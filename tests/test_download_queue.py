from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import pytest


LIB_ROOT = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(LIB_ROOT))

from tmux_opener_downloads import (  # noqa: E402
    MAX_HISTORY,
    TERMINAL_STATES,
    WORKERS,
    DownloadQueue,
)


def wait_for(predicate: Callable[[], object], timeout: float = 3) -> object:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.01)
    raise AssertionError("condition was not reached before timeout")


def stored_record(identifier: str, state: str, host: str = "devbox") -> dict[str, object]:
    return {
        "id": identifier,
        "ssh_host": host,
        "path": f"/remote/{identifier}.bin",
        "ask_destination": False,
        "size_bytes": None,
        "bytes_received": 0,
        "destination": None,
        "state": state,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "error": None,
    }


def test_queue_limits_workers_and_persists_progress(tmp_path: Path) -> None:
    storage = tmp_path / "history.json"
    lock = threading.Lock()
    release = threading.Event()
    entered = threading.Event()
    active = 0
    max_active = 0
    entered_count = 0

    def transfer(job: dict[str, object], update: Callable[..., None], _cancel: threading.Event) -> dict[str, object]:
        nonlocal active, max_active, entered_count
        with lock:
            active += 1
            max_active = max(max_active, active)
            entered_count += 1
            if entered_count == WORKERS:
                entered.set()
        update(bytes_received=7)
        release.wait(timeout=5)
        with lock:
            active -= 1
        return {
            "state": "completed",
            "bytes_received": 7,
            "destination": f"/Downloads/{Path(str(job['path'])).name}",
            "error": None,
        }

    queue = DownloadQueue(storage, transfer)
    try:
        jobs = [
            queue.submit("devbox", f"/remote/file-{index}.bin", False, size_bytes=10)
            for index in range(3)
        ]
        assert entered.wait(timeout=2)

        current = {job["id"]: job for job in queue.snapshot()}
        assert sum(job["state"] == "downloading" for job in current.values()) == WORKERS
        assert sum(job["state"] == "queued" for job in current.values()) == 1
        with lock:
            assert max_active == WORKERS

        release.set()
        wait_for(lambda: all(job["state"] == "completed" for job in queue.snapshot()))
        snapshot = queue.snapshot()
        assert [job["id"] for job in snapshot] == [job["id"] for job in reversed(jobs)]
        assert all(job["bytes_received"] == 7 for job in snapshot)
        assert all(job["id"] in {value["id"] for value in jobs} for job in snapshot)
        persisted = json.loads(storage.read_text(encoding="utf-8"))
        assert {record["state"] for record in persisted} == {"completed"}
        assert storage.stat().st_mode & 0o777 == 0o600
    finally:
        release.set()
        queue.close()


def test_restart_marks_unfinished_records_interrupted(tmp_path: Path) -> None:
    storage = tmp_path / "history.json"
    records = [
        stored_record("running", "downloading"),
        stored_record("queued", "queued"),
        stored_record("done", "completed"),
    ]
    storage.write_text(json.dumps(records), encoding="utf-8")

    queue = DownloadQueue(storage, lambda *_args: {"state": "completed"})
    try:
        snapshot = queue.snapshot()
        by_id = {record["id"]: record for record in snapshot}
        assert by_id["running"]["state"] == "interrupted"
        assert by_id["queued"]["state"] == "interrupted"
        assert by_id["done"]["state"] == "completed"
        assert by_id["running"]["error"] == "Client stopped before this transfer completed"
        persisted = json.loads(storage.read_text(encoding="utf-8"))
        assert {record["state"] for record in persisted} == {"interrupted", "completed"}
        assert storage.stat().st_mode & 0o777 == 0o600
    finally:
        queue.close()


def test_history_keeps_at_most_latest_terminal_records(tmp_path: Path) -> None:
    storage = tmp_path / "history.json"
    records = [stored_record(f"job-{index}", "completed") for index in range(MAX_HISTORY + 1)]
    storage.write_text(json.dumps(records), encoding="utf-8")

    queue = DownloadQueue(storage, lambda *_args: {"state": "completed"})
    try:
        snapshot = queue.snapshot()
        assert len(snapshot) == MAX_HISTORY
        assert snapshot[0]["id"] == f"job-{MAX_HISTORY}"
        assert snapshot[-1]["id"] == "job-1"
    finally:
        queue.close()


def test_cancel_scopes_to_host_and_handles_queued_and_active_jobs(tmp_path: Path) -> None:
    started = threading.Event()
    lock = threading.Lock()
    active_ids: list[str] = []

    def transfer(job: dict[str, object], _update: Callable[..., None], cancel: threading.Event) -> dict[str, object]:
        with lock:
            active_ids.append(str(job["id"]))
            if len(active_ids) == WORKERS:
                started.set()
        cancel.wait(timeout=5)
        return {"state": "cancelled", "bytes_received": 0, "error": "cancelled by test"}

    queue = DownloadQueue(tmp_path / "history.json", transfer)
    try:
        jobs = [queue.submit("devbox", f"/remote/file-{index}.bin", False) for index in range(3)]
        assert started.wait(timeout=2)
        queued_id = jobs[2]["id"]
        active_id = jobs[0]["id"]

        with pytest.raises(ValueError, match="not found for this host"):
            queue.cancel(active_id, "other-host")
        queued_result = queue.cancel(queued_id, "devbox")
        assert queued_result["state"] == "cancelled"
        active_result = queue.cancel(active_id, "devbox")
        assert active_result["state"] == "downloading"

        wait_for(
            lambda: {
                record["id"]: record["state"]
                for record in queue.snapshot()
            }
            if all(
                record["state"] in TERMINAL_STATES
                for record in queue.snapshot()
                if record["id"] in {active_id, queued_id}
            )
            else None
        )
        states = {record["id"]: record["state"] for record in queue.snapshot()}
        assert states[active_id] == "cancelled"
        assert states[queued_id] == "cancelled"
        with lock:
            assert queued_id not in active_ids
    finally:
        queue.close()


def test_retry_creates_new_id_and_rejects_wrong_host(tmp_path: Path) -> None:
    attempts: dict[str, int] = {}

    def transfer(job: dict[str, object], _update: Callable[..., None], _cancel: threading.Event) -> dict[str, object]:
        identifier = str(job["id"])
        attempts[identifier] = attempts.get(identifier, 0) + 1
        if len(attempts) == 1:
            return {"state": "failed", "error": "synthetic failure", "bytes_received": 2}
        return {
            "state": "completed",
            "bytes_received": 4,
            "destination": "/Downloads/retried.bin",
            "error": None,
        }

    queue = DownloadQueue(tmp_path / "history.json", transfer)
    try:
        original = queue.submit("devbox", "/remote/retry.bin", False, size_bytes=4)
        wait_for(lambda: next((record for record in queue.snapshot() if record["id"] == original["id"] and record["state"] == "failed"), None))
        failed = next(record for record in queue.snapshot() if record["id"] == original["id"])
        assert failed["error"] == "synthetic failure"

        with pytest.raises(ValueError, match="not found for this host"):
            queue.retry(original["id"], "other-host")
        retried = queue.retry(original["id"], "devbox")
        assert retried["id"] != original["id"]
        assert retried["state"] == "queued"
        wait_for(lambda: next((record for record in queue.snapshot() if record["id"] == retried["id"] and record["state"] == "completed"), None))
        assert queue.snapshot("other-host") == []
        assert queue.snapshot("devbox")[0]["id"] == retried["id"]
    finally:
        queue.close()


def test_close_cancels_active_workers_and_interrupts_queued_jobs(tmp_path: Path) -> None:
    started = threading.Event()
    active_ids: list[str] = []
    lock = threading.Lock()

    def transfer(job: dict[str, object], _update: Callable[..., None], cancel: threading.Event) -> dict[str, object]:
        with lock:
            active_ids.append(str(job["id"]))
            if len(active_ids) == WORKERS:
                started.set()
        cancel.wait(timeout=5)
        return {"state": "cancelled", "error": "stopped"}

    queue = DownloadQueue(tmp_path / "history.json", transfer)
    try:
        jobs = [queue.submit("devbox", f"/remote/stop-{index}.bin", False) for index in range(3)]
        assert started.wait(timeout=2)
        queue.close()
        states = {record["id"]: record["state"] for record in queue.snapshot()}
        assert all(states[identifier] == "interrupted" for identifier in active_ids)
        assert states[jobs[2]["id"]] == "interrupted"
        with pytest.raises(ValueError, match="stopping"):
            queue.submit("devbox", "/remote/after-close.bin", False)
    finally:
        if not queue.closing:
            queue.close()
