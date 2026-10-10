"""A bounded, persistent download queue owned by one local client."""

from __future__ import annotations

import json
import os
import queue
import stat
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


TERMINAL_STATES = {"completed", "failed", "cancelled", "interrupted"}
MAX_PENDING = 100
MAX_HISTORY = 100
WORKERS = 2


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DownloadQueue:
    def __init__(self, storage: Path, transfer: Callable):
        self.storage = storage
        self.transfer = transfer
        self.lock = threading.RLock()
        self.pending: queue.Queue[str | None] = queue.Queue()
        self.jobs: dict[str, dict] = {}
        self.cancel_events: dict[str, threading.Event] = {}
        self.closing = False
        self.storage_error: str | None = None
        self.storage.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            fd = os.open(storage, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            pass
        else:
            with os.fdopen(fd, "r", encoding="utf-8") as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
                    raise ValueError("unsafe download history file")
                records = json.load(handle)
                if not isinstance(records, list):
                    raise ValueError("invalid download history")
                self.jobs = {record["id"]: record for record in records}
            for record in self.jobs.values():
                if record["state"] not in TERMINAL_STATES:
                    record.update(state="interrupted", error="Client stopped before this transfer completed", updated_at=timestamp())
            self._save()
        self.workers = [threading.Thread(target=self._work, name=f"download-{index}") for index in range(WORKERS)]
        for worker in self.workers:
            worker.start()

    def _save(self) -> None:
        # Called while holding the queue lock; replace the history with a private file.
        while len(self.jobs) > MAX_HISTORY:
            oldest = next((key for key, value in self.jobs.items() if value["state"] in TERMINAL_STATES), None)
            if oldest is None:
                break
            del self.jobs[oldest]
            self.cancel_events.pop(oldest, None)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.storage.parent,
                                             prefix=".downloads-", delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(list(self.jobs.values()), handle, ensure_ascii=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.storage)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    def _save_worker_state(self) -> None:
        try:
            self._save()
            self.storage_error = None
        except OSError:
            # Keep the queue and live status usable if the state disk fills up.
            self.storage_error = "Could not persist download history; check free disk space and permissions"

    def submit(self, host: str, path: str, ask_destination: bool, size_bytes: int | None = None,
               preview: bool = False) -> dict:
        with self.lock:
            if self.closing:
                raise ValueError("download queue is stopping")
            if sum(job["state"] not in TERMINAL_STATES for job in self.jobs.values()) >= MAX_PENDING:
                raise ValueError("download queue is full")
            identifier = uuid.uuid4().hex
            created = timestamp()
            record = {"id": identifier, "ssh_host": host, "path": path, "ask_destination": ask_destination,
                      "preview": preview, "size_bytes": size_bytes, "bytes_received": 0, "destination": None,
                      "state": "queued", "created_at": created, "updated_at": created, "error": None}
            self.jobs[identifier] = record
            self.cancel_events[identifier] = threading.Event()
            try:
                self._save()
            except OSError:
                del self.jobs[identifier]
                del self.cancel_events[identifier]
                raise
            self.pending.put(identifier)
            return dict(record)

    def snapshot(self, host: str | None = None) -> list[dict]:
        with self.lock:
            return [dict(record) for record in reversed(list(self.jobs.values()))
                    if host is None or record["ssh_host"] == host]

    def cancel(self, identifier: str, host: str) -> dict:
        with self.lock:
            record = self._find(identifier, host)
            if record["state"] not in TERMINAL_STATES:
                self.cancel_events[identifier].set()
                # Active workers keep their partial copy so a retry resumes it.
                if record["state"] == "queued":
                    record.update(state="cancelled", updated_at=timestamp())
                    self._save()
            return dict(record)

    def retry(self, identifier: str, host: str) -> dict:
        with self.lock:
            record = self._find(identifier, host)
            if record["state"] not in {"failed", "cancelled", "interrupted"}:
                raise ValueError("only failed, cancelled or interrupted downloads can be retried")
            return self.submit(record["ssh_host"], record["path"], record["ask_destination"], record["size_bytes"],
                               record.get("preview", False))

    def _find(self, identifier: str, host: str) -> dict:
        record = self.jobs.get(identifier)
        if record is None or record["ssh_host"] != host:
            raise ValueError("download was not found for this host")
        return record

    def _work(self) -> None:
        while True:
            identifier = self.pending.get()
            if identifier is None:
                return
            with self.lock:
                record = self.jobs.get(identifier)
                if record is None or record["state"] in TERMINAL_STATES:
                    continue
                event = self.cancel_events[identifier]
                record.update(state="choosing_destination" if record["ask_destination"] else "downloading",
                              updated_at=timestamp())
                self._save_worker_state()
                job = dict(record)
            last_saved = 0.0

            def update(**fields) -> None:
                nonlocal last_saved
                with self.lock:
                    current = self.jobs[identifier]
                    previous_state = current["state"]
                    current.update(fields, updated_at=timestamp())
                    now = time.monotonic()
                    if now - last_saved >= 0.5 or current["state"] != previous_state:
                        self._save_worker_state()
                        last_saved = now

            try:
                result = self.transfer(job, update, event)
            except Exception:
                result = {"state": "failed", "error": "Download worker failed"}
            with self.lock:
                if self.closing and result.get("state") == "cancelled":
                    result.update(state="interrupted", error="Client stopped during download")
                self.jobs[identifier].update(result, updated_at=timestamp())
                self._save_worker_state()

    def close(self) -> None:
        with self.lock:
            self.closing = True
            for identifier, record in self.jobs.items():
                if record["state"] not in TERMINAL_STATES:
                    self.cancel_events[identifier].set()
                    if record["state"] == "queued":
                        record.update(state="interrupted", error="Client stopped before download started", updated_at=timestamp())
            self._save_worker_state()
            for _ in self.workers:
                self.pending.put(None)
        for worker in self.workers:
            worker.join(timeout=5)
