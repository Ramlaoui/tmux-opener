from __future__ import annotations

import json
import os
import runpy
import socket
import subprocess
import sys
import threading
import time
from argparse import Namespace
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

# Runs the remote command on this machine with the upload on stdin, the way sshd would.
FAKE_SSH = f"""#!{sys.executable}
import json, os, sys
args = sys.argv[1:]
index = args.index("--") + 2
capture = os.environ.get("FAKE_SSH_CAPTURE")
if capture:
    with open(capture, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(args[index - 1:]) + "\\n")
os.execv("/bin/sh", ["sh", "-c", " ".join(args[index:])])
"""


@pytest.fixture
def client(monkeypatch: Any, tmp_path: Path) -> dict[str, Any]:
    module = runpy.run_path(str(ROOT / "bin/tmux-opener-client"))
    notifications: list[str] = []
    monkeypatch.setitem(module["upload_files"].__globals__, "download_notification", notifications.append)
    monkeypatch.setenv("FAKE_SSH_CAPTURE", str(tmp_path / "ssh-calls.jsonl"))
    module["notifications"] = notifications
    return module


@pytest.fixture
def fake_ssh(tmp_path: Path) -> str:
    path = tmp_path / "fake-ssh"
    path.write_text(FAKE_SSH, encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def pick(client: dict[str, Any], monkeypatch: Any, files: list[Path] | None) -> list[str]:
    prompts: list[str] = []

    def choose(prompt: str, _cancel: threading.Event) -> list[Path] | None:
        prompts.append(prompt)
        return files

    monkeypatch.setitem(client["upload_files"].__globals__, "ask_upload_files", choose)
    return prompts


def test_upload_publishes_picked_files_without_replacing_remote_files(
    client: dict[str, Any], fake_ssh: str, monkeypatch: Any, tmp_path: Path,
) -> None:
    remote = tmp_path / "remote dir"
    remote.mkdir()
    (remote / "notes.txt").write_text("keep me", encoding="utf-8")
    local = tmp_path / "local"
    local.mkdir()
    files = [local / "notes.txt", local / "it's $HOME.tar.gz", local / "-dash", local / "empty.bin"]
    files[0].write_text("new notes", encoding="utf-8")
    files[1].write_bytes(os.urandom(700_000))
    files[2].write_text("dash", encoding="utf-8")
    files[3].touch()
    prompts = pick(client, monkeypatch, files)
    updates: list[dict[str, object]] = []

    result = client["upload_files"]("devbox", str(remote), None, fake_ssh, progress=lambda **fields: updates.append(fields))

    assert result == {"state": "completed", "destination": str(remote), "bytes_received": 700_000 + 9 + 4,
                      "error": None}
    assert prompts == [f"Upload to devbox:{remote}"]
    assert (remote / "notes.txt").read_text(encoding="utf-8") == "keep me"
    assert (remote / "notes (1).txt").read_text(encoding="utf-8") == "new notes"
    assert (remote / "it's $HOME.tar.gz").read_bytes() == files[1].read_bytes()
    assert (remote / "-dash").read_text(encoding="utf-8") == "dash"
    assert (remote / "empty.bin").read_bytes() == b""
    assert not list(remote.glob(".tmux-opener-upload-*"))
    assert {"files": [str(path) for path in files], "file_count": 4, "ask_destination": False} in updates
    assert updates[-1] == {"files": []}
    assert client["notifications"] == [f"Uploaded 4 files to devbox:{remote}"]


def test_single_upload_reports_the_published_path(
    client: dict[str, Any], fake_ssh: str, monkeypatch: Any, tmp_path: Path,
) -> None:
    remote = tmp_path / "remote"
    remote.mkdir()
    (remote / "archive.tar.gz").touch()
    source = tmp_path / "archive.tar.gz"
    source.write_bytes(b"bytes")

    result = client["upload_files"]("devbox", str(remote), [str(source)], fake_ssh)

    assert result["destination"] == str(remote / "archive.tar (1).gz")
    assert client["notifications"] == [f"Uploaded archive.tar (1).gz to devbox:{remote}"]


def test_cancelled_picker_starts_no_ssh(client: dict[str, Any], fake_ssh: str, monkeypatch: Any, tmp_path: Path) -> None:
    pick(client, monkeypatch, None)

    assert client["upload_files"]("devbox", str(tmp_path), None, fake_ssh) == {"state": "cancelled"}
    assert not (tmp_path / "ssh-calls.jsonl").exists()


def test_failures_name_the_cause_without_local_paths(
    client: dict[str, Any], fake_ssh: str, tmp_path: Path,
) -> None:
    source = tmp_path / "private" / "data.csv"
    source.parent.mkdir()
    source.write_text("1,2\n", encoding="utf-8")

    missing = client["upload_files"]("devbox", str(tmp_path / "gone"), [str(source)], fake_ssh)
    unreadable = client["upload_files"]("devbox", str(tmp_path), [str(tmp_path / "private" / "lost.csv")], fake_ssh)
    folder = client["upload_files"]("devbox", str(tmp_path), [str(source.parent)], fake_ssh)

    assert missing["state"] == "failed" and "does not exist" in missing["error"]
    assert unreadable["error"] == "cannot read lost.csv: No such file or directory"
    assert folder["error"] == "only regular files can be uploaded: private"
    assert all(str(source.parent) not in message for message in client["notifications"][1:])
    assert all(message.startswith("Upload failed") for message in client["notifications"])


def test_remote_script_discards_incomplete_uploads(client: dict[str, Any], tmp_path: Path) -> None:
    result = subprocess.run(["sh", "-c", client["UPLOAD_SCRIPT"], "sh", str(tmp_path), "short.bin", "10", "abc"],
                            input=b"12345", capture_output=True, check=False)

    assert result.returncode == 4
    assert list(tmp_path.iterdir()) == []


def test_cancel_stops_the_upload_and_removes_the_remote_temporary(
    client: dict[str, Any], fake_ssh: str, tmp_path: Path,
) -> None:
    remote = tmp_path / "remote"
    remote.mkdir()
    source = tmp_path / "big.bin"
    source.write_bytes(os.urandom(4 << 20))
    cancel = threading.Event()

    def progress(**fields: object) -> None:
        if fields.get("bytes_received"):
            cancel.set()

    result = client["upload_files"]("devbox", str(remote), [str(source)], fake_ssh, progress=progress, cancel=cancel)

    assert result["state"] == "cancelled"
    deadline = time.monotonic() + 3
    while list(remote.iterdir()) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert list(remote.iterdir()) == []


class FakeQueue:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    def submit(self, *args: object, **kwargs: object) -> dict[str, object]:
        self.calls.append((args, kwargs))
        return {"id": "job-1"}


def client_args(**overrides: object) -> Namespace:
    values = {"allow_any_ssh_host": False, "allow_ssh_host": ["devbox"], "default_ssh_host": None,
              "dry_run": False, "verbose": False, "download_queue": FakeQueue()}
    values.update(overrides)
    return Namespace(**values)


def test_dispatch_queues_uploads_and_ignores_remote_file_lists(client: dict[str, Any]) -> None:
    args = client_args()
    request = {"version": 1, "action": "upload_files", "ssh_host": "devbox", "path": "/home/me/project",
               "files": ["/local/.ssh/id_ed25519"]}

    assert client["dispatch"](request, args) == {"download_id": "job-1", "state": "queued"}
    assert args.download_queue.calls == [(("devbox", "/home/me/project", True), {"kind": "upload"})]
    for bad in ({"path": "relative/dir"}, {"ssh_host": "elsewhere"}, {"path": "/a\nb"}):
        with pytest.raises(client["RequestError"]):
            client["dispatch"]({**request, **bad}, args)
    assert "upload_files" in client["ping_response"](args)["capabilities"]


def test_transfer_job_asks_first_then_retries_the_remaining_files(client: dict[str, Any], monkeypatch: Any) -> None:
    calls = []
    monkeypatch.setitem(client["transfer_job"].__globals__, "upload_files",
                        lambda host, path, files, *_args, **_kwargs: calls.append((host, path, files)) or {})
    args = Namespace(ssh_config=None, verbose=False)
    job = {"kind": "upload", "ssh_host": "devbox", "path": "/dir", "ask_destination": True, "files": None}

    client["transfer_job"](job, None, threading.Event(), args)
    client["transfer_job"]({**job, "ask_destination": False, "files": ["/local/b"]}, None, threading.Event(), args)

    assert calls == [("devbox", "/dir", None), ("devbox", "/dir", ["/local/b"])]


def test_queue_shows_upload_states(tmp_path: Path) -> None:
    from tmux_opener_downloads import DownloadQueue

    states = []
    queue = DownloadQueue(tmp_path / "downloads.json",
                          lambda job, update, cancel: states.append(job["state"]) or {"state": "failed"})
    try:
        job = queue.submit("devbox", "/dir", True, kind="upload")
        deadline = time.monotonic() + 5
        while queue.snapshot()[0]["state"] != "failed" and time.monotonic() < deadline:
            time.sleep(0.01)
        queue.jobs[job["id"]]["ask_destination"] = False
        queue.retry(job["id"], "devbox")
        while len(states) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        queue.close()
    assert states == ["choosing_files", "uploading"]


def serve_bridge(socket_path: Path, capabilities: list[str], requests: list[dict], stop: threading.Event) -> threading.Thread:
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    server.listen()
    server.settimeout(0.1)

    def receive() -> None:
        with server:
            while not stop.is_set():
                try:
                    connection, _ = server.accept()
                except TimeoutError:
                    continue
                with connection:
                    requests.append(json.loads(connection.recv(1 << 20)))
                    connection.sendall(json.dumps({"version": 1, "ok": True, "client": "tmux-opener-client",
                                                   "capabilities": capabilities}).encode() + b"\n")

    thread = threading.Thread(target=receive)
    thread.start()
    return thread


def run_dispatch(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/tmux-opener-dispatch"), "--upload", "--ssh-host", "devbox",
         "--no-log", "--route-feedback", "never", *args],
        text=True, capture_output=True, timeout=5, stdin=subprocess.DEVNULL, env={"PATH": "/usr/bin:/bin"},
    )


@pytest.mark.parametrize("capable", [True, False])
def test_dispatch_upload_sends_the_pane_directory(tmp_path: Path, capable: bool) -> None:
    socket_path = tmp_path / "client.sock"
    requests: list[dict] = []
    stop = threading.Event()
    thread = serve_bridge(socket_path, ["upload_files"] if capable else ["download_folder"], requests, stop)

    result = run_dispatch("--socket", str(socket_path), "--cwd", str(tmp_path))
    stop.set()
    thread.join(timeout=5)

    sent = [request for request in requests if request["action"] != "ping"]
    if not capable:
        assert result.returncode == 1
        assert "cannot upload files" in result.stderr
        assert sent == []
        return
    assert result.returncode == 0, result.stderr
    assert sent[0].pop("host_info")["cwd"] == str(tmp_path)
    assert sent == [{"version": 1, "action": "upload_files", "path": str(tmp_path), "ssh_host": "devbox"}]


def test_dispatch_upload_refuses_missing_folders(tmp_path: Path) -> None:
    result = run_dispatch("--socket", str(tmp_path / "client.sock"), "--cwd", str(tmp_path / "gone"))

    assert result.returncode == 1
    assert "not a writable folder" in result.stderr
