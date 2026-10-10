from __future__ import annotations

import filecmp
import io
import json
import os
import runpy
import shutil
import socket
import subprocess
import sys
import tarfile
import threading
import time
from argparse import Namespace
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from tmux_opener_common import MAX_GLOB_FILES, build_download_requests  # noqa: E402

# Runs the remote command on this machine, the way sshd would hand it to a shell.
FAKE_SSH = f"""#!{sys.executable}
import json, os, sys, time
from pathlib import Path
args = sys.argv[1:]
index = 0
while index < len(args):
    if args[index] == "--":
        index += 1
        break
    if args[index] in ("-F", "-S", "-o"):
        index += 2
        continue
    if not args[index].startswith("-"):
        break
    index += 1
capture = os.environ.get("FAKE_SSH_CAPTURE")
if capture:
    with open(capture, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(args[index:]) + "\\n")
gate = os.environ.get("FAKE_SSH_GATE")
while gate and not Path(gate).exists():
    time.sleep(0.01)
if os.environ.get("FAKE_SSH_ARCHIVE"):
    sys.stdout.buffer.write(Path(os.environ["FAKE_SSH_ARCHIVE"]).read_bytes())
    raise SystemExit(0)
os.execv("/bin/sh", ["sh", "-c", " ".join(args[index + 1:])])
"""


@pytest.fixture
def client(monkeypatch: Any, tmp_path: Path) -> dict[str, Any]:
    module = runpy.run_path(str(ROOT / "bin/tmux-opener-client"))
    downloads = tmp_path / "Downloads"
    monkeypatch.setitem(module["download_folder"].__globals__, "downloads_directory", lambda: downloads)
    monkeypatch.setitem(module["download_folder"].__globals__, "download_notification", lambda _message: None)
    monkeypatch.setenv("FAKE_SSH_CAPTURE", str(tmp_path / "ssh-calls.jsonl"))
    return module


@pytest.fixture
def fake_ssh(tmp_path: Path) -> str:
    path = tmp_path / "fake-ssh"
    path.write_text(FAKE_SSH, encoding="utf-8")
    path.chmod(0o755)
    return str(path)


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "remote" / "exp 42"
    (root / "nested" / "deep").mkdir(parents=True)
    (root / "empty").mkdir()
    (root / "metrics.csv").write_text("step,loss\n1,0.5\n", encoding="utf-8")
    (root / "-starts-with-dash.txt").write_text("dash", encoding="utf-8")
    (root / "nested" / "weights.bin").write_bytes(os.urandom(300_000))
    (root / "nested" / "deep" / "it's;$HOME.png").write_bytes(b"\x89PNG\x00\xff")
    (root / "nested" / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (root / "nested" / "run.sh").chmod(0o755)
    os.symlink("weights.bin", root / "nested" / "latest")
    return root


def same_tree(left: Path, right: Path) -> bool:
    comparison = filecmp.dircmp(left, right)
    return (not comparison.left_only and not comparison.right_only and not comparison.funny_files
            and not filecmp.cmpfiles(left, right, comparison.common_files, shallow=False)[1]
            and all(same_tree(left / name, right / name) for name in comparison.common_dirs))


def no_partials(directory: Path) -> bool:
    return not list(directory.glob(".tmux-opener-*"))


def without_rsync(client: dict[str, Any], monkeypatch: Any) -> None:
    monkeypatch.setitem(client["download_folder"].__globals__, "local_rsync", lambda: None)


@pytest.mark.parametrize("transport", ["tar", "rsync"])
def test_folder_download_copies_tree_byte_identically(
    client: dict[str, Any], fake_ssh: str, tree: Path, tmp_path: Path, monkeypatch: Any, transport: str,
) -> None:
    if transport == "tar":
        without_rsync(client, monkeypatch)
    elif client["local_rsync"]() is None:
        pytest.skip("rsync 3 is not installed")
    updates: list[dict[str, object]] = []

    result = client["download_folder"]("devbox", str(tree), None, False, fake_ssh,
                                       progress=lambda **fields: updates.append(fields))

    destination = tmp_path / "Downloads" / "exp 42"
    assert result["state"] == "completed", result
    assert result["destination"] == str(destination)
    assert result["bytes_received"] == 300_000 + 16 + 4 + 6 + 10
    assert same_tree(tree, destination)
    assert os.readlink(destination / "nested" / "latest") == "weights.bin"
    assert os.access(destination / "nested" / "run.sh", os.X_OK)
    assert updates[0] == {"state": "downloading", "destination": str(destination)}
    assert no_partials(tmp_path / "Downloads")
    calls = [json.loads(line) for line in (tmp_path / "ssh-calls.jsonl").read_text().splitlines()]
    assert calls[-1][0] == "devbox"
    assert calls[-1][1].split()[0] == transport


def test_remote_without_rsync_falls_back_to_tar(
    client: dict[str, Any], fake_ssh: str, tree: Path, tmp_path: Path, monkeypatch: Any,
) -> None:
    if client["local_rsync"]() is None:
        pytest.skip("rsync 3 is not installed")
    # The fake remote shell inherits PATH: it finds tar but no rsync.
    remote_bin = tmp_path / "remote-bin"
    remote_bin.mkdir()
    os.symlink(shutil.which("tar"), remote_bin / "tar")
    rsync = client["local_rsync"]()
    monkeypatch.setitem(client["download_folder"].__globals__, "local_rsync", lambda: rsync)
    monkeypatch.setenv("PATH", str(remote_bin))

    result = client["download_folder"]("devbox", str(tree), None, False, fake_ssh)

    assert result["state"] == "completed", result
    assert same_tree(tree, tmp_path / "Downloads" / "exp 42")


@pytest.mark.parametrize("transport", ["tar", "rsync"])
def test_glob_download_copies_only_listed_files(
    client: dict[str, Any], fake_ssh: str, tree: Path, tmp_path: Path, monkeypatch: Any, transport: str,
) -> None:
    if transport == "tar":
        without_rsync(client, monkeypatch)
    elif client["local_rsync"]() is None:
        pytest.skip("rsync 3 is not installed")
    files = ["-starts-with-dash.txt", "nested/deep/it's;$HOME.png"]

    result = client["download_folder"]("devbox", str(tree), files, False, fake_ssh)

    destination = tmp_path / "Downloads" / "exp 42"
    assert result["state"] == "completed", result
    assert sorted(str(path.relative_to(destination)) for path in destination.rglob("*") if path.is_file()) == sorted(files)
    assert (destination / files[1]).read_bytes() == b"\x89PNG\x00\xff"


def test_existing_folder_gets_numbered_name(
    client: dict[str, Any], fake_ssh: str, tree: Path, tmp_path: Path, monkeypatch: Any,
) -> None:
    without_rsync(client, monkeypatch)
    existing = tmp_path / "Downloads" / "exp 42"
    existing.mkdir(parents=True)
    (existing / "keep.txt").write_text("mine", encoding="utf-8")

    result = client["download_folder"]("devbox", str(tree), None, False, fake_ssh)

    assert result["destination"] == str(tmp_path / "Downloads" / "exp 42 (1)")
    assert (existing / "keep.txt").read_text(encoding="utf-8") == "mine"


@pytest.mark.parametrize("name, linkname", [("../escaped.txt", None), ("ok/evil", "../../escaped.txt"),
                                            ("ok/evil", "/tmp")])
def test_tar_entries_outside_the_folder_are_never_written(
    client: dict[str, Any], fake_ssh: str, tmp_path: Path, monkeypatch: Any, name: str, linkname: str | None,
) -> None:
    without_rsync(client, monkeypatch)
    archive = tmp_path / "evil.tar"
    with tarfile.open(archive, "w") as handle:
        member = tarfile.TarInfo(name)
        if linkname:
            member.type, member.linkname = tarfile.SYMTYPE, linkname
            handle.addfile(member)
            # A later write through the skipped link must not escape either.
            member = tarfile.TarInfo("ok/evil")
        member.size = 4
        handle.addfile(member, io.BytesIO(b"evil"))
    monkeypatch.setenv("FAKE_SSH_ARCHIVE", str(archive))

    result = client["download_folder"]("devbox", "/remote/folder", None, False, fake_ssh)

    assert not (tmp_path / "escaped.txt").exists()
    if linkname:
        assert result["state"] == "completed", result
        assert (tmp_path / "Downloads" / "folder" / "ok" / "evil").read_bytes() == b"evil"
    else:
        assert result["state"] == "failed"
        assert "unsafe entry" in result["error"]
        assert not (tmp_path / "Downloads" / "folder").exists()
    assert no_partials(tmp_path / "Downloads")


@pytest.mark.parametrize("transport", ["tar", "rsync"])
def test_cancel_stops_transfer_and_removes_partial_data(
    client: dict[str, Any], fake_ssh: str, tree: Path, tmp_path: Path, monkeypatch: Any, transport: str,
) -> None:
    if transport == "tar":
        without_rsync(client, monkeypatch)
    elif client["local_rsync"]() is None:
        pytest.skip("rsync 3 is not installed")
    gate = tmp_path / "gate"
    monkeypatch.setenv("FAKE_SSH_GATE", str(gate))
    cancel = threading.Event()
    threading.Timer(0.5, cancel.set).start()
    started = time.monotonic()

    try:
        result = client["download_folder"]("devbox", str(tree), None, False, fake_ssh, cancel=cancel)
    finally:
        gate.touch()  # release a fake ssh orphaned by rsync

    assert result["state"] == "cancelled"
    assert time.monotonic() - started < 5
    assert not (tmp_path / "Downloads" / "exp 42").exists()
    assert no_partials(tmp_path / "Downloads")


def test_failed_rsync_keeps_partial_data_for_resume(
    client: dict[str, Any], fake_ssh: str, tmp_path: Path,
) -> None:
    if client["local_rsync"]() is None:
        pytest.skip("rsync 3 is not installed")

    result = client["download_folder"]("devbox", str(tmp_path / "missing"), None, False, fake_ssh)

    assert result["state"] == "failed"
    assert "rsync exited" in result["error"]
    assert not no_partials(tmp_path / "Downloads")


def client_args(**overrides: object) -> Namespace:
    values = {"allow_any_ssh_host": False, "allow_ssh_host": ["devbox"], "default_ssh_host": None,
              "dry_run": False, "verbose": False}
    values.update(overrides)
    return Namespace(**values)


class FakeQueue:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    def submit(self, *args: object, **kwargs: object) -> dict[str, object]:
        self.calls.append((args, kwargs))
        return {"id": "job-1"}


def test_dispatch_queues_folder_jobs_and_validates_glob_files(client: dict[str, Any]) -> None:
    args = client_args(download_queue=FakeQueue())
    request = {"version": 1, "action": "download_folder", "ssh_host": "devbox", "path": "/runs/exp-42",
               "files": ["a.png", "sub/b.png", "a.png"], "size_bytes": 10, "file_count": 2}

    assert client["dispatch"](request, args) == {"download_id": "job-1", "state": "queued"}
    assert args.download_queue.calls == [(("devbox", "/runs/exp-42", False, 10, False),
                                          {"kind": "folder", "files": ["a.png", "sub/b.png"], "file_count": 2})]
    for files in (["../secret"], ["/etc/passwd"], ["a\nb"], [], ["x"] * 1001, "a.png"):
        with pytest.raises(client["RequestError"], match="files must"):
            client["dispatch"]({**request, "files": files}, args)
    assert "download_folder" in client["ping_response"](args)["capabilities"]


def test_retry_keeps_folder_fields(client: dict[str, Any], tmp_path: Path) -> None:
    from tmux_opener_downloads import DownloadQueue

    gate = threading.Event()
    queue = DownloadQueue(tmp_path / "downloads.json", lambda job, update, cancel: (gate.wait(5), {"state": "failed"})[1])
    try:
        job = queue.submit("devbox", "/runs", False, 5, kind="folder", files=["a"], file_count=1)
        gate.set()
        deadline = time.monotonic() + 5
        while queue.snapshot()[0]["state"] != "failed" and time.monotonic() < deadline:
            time.sleep(0.01)
        retried = queue.retry(job["id"], "devbox")
        assert (retried["kind"], retried["files"], retried["file_count"]) == ("folder", ["a"], 1)
    finally:
        queue.close()


def touch(path: Path, data: bytes = b"") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_selection_builds_folder_and_glob_requests(tmp_path: Path) -> None:
    folder = tmp_path / "runs" / "exp-42"
    touch(folder / "a.png")
    touch(folder / "b.png")
    touch(folder / "notes.txt")
    touch(tmp_path / "runs" / "exp-43" / "c.png")

    assert build_download_requests("runs/exp-42\nruns/*/[ab].png runs/exp-4?/c.png", str(tmp_path), "devbox") == [
        {"version": 1, "action": "download_folder", "path": str(folder), "ask_destination": False,
         "ssh_host": "devbox"},
        {"version": 1, "action": "download_folder", "path": str(tmp_path / "runs"), "ask_destination": False,
         "files": ["exp-42/a.png", "exp-42/b.png"], "ssh_host": "devbox"},
        {"version": 1, "action": "download_folder", "path": str(tmp_path / "runs"), "ask_destination": False,
         "files": ["exp-43/c.png"], "ssh_host": "devbox"},
    ]
    assert build_download_requests("runs/*.missing", str(tmp_path), "devbox") is None


def test_glob_over_the_file_cap_is_refused(tmp_path: Path) -> None:
    for index in range(MAX_GLOB_FILES + 1):
        touch(tmp_path / "many" / f"{index}.txt")

    with pytest.raises(ValueError, match="more than 1000 files"):
        build_download_requests("many/*.txt", str(tmp_path), "devbox")


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
                    request = json.loads(connection.recv(1 << 20))
                    requests.append(request)
                    connection.sendall(json.dumps({"version": 1, "ok": True, "client": "tmux-opener-client",
                                                   "capabilities": capabilities}).encode() + b"\n")

    thread = threading.Thread(target=receive)
    thread.start()
    return thread


@pytest.mark.parametrize("capable", [True, False])
def test_dispatch_sends_folder_sizes_and_refuses_old_clients(tmp_path: Path, capable: bool) -> None:
    folder = tmp_path / "exp-42"
    touch(folder / "a.png", b"12345")
    touch(folder / "sub" / "b.png", b"123")
    os.symlink("a.png", folder / "link.png")
    socket_path = tmp_path / "client.sock"
    requests: list[dict] = []
    stop = threading.Event()
    thread = serve_bridge(socket_path, ["download_folder"] if capable else ["remote_pdf"], requests, stop)

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/tmux-opener-dispatch"), "--download", "--socket", str(socket_path),
         "--cwd", str(tmp_path), "--ssh-host", "devbox", "--no-log", "--route-feedback", "never"],
        input="exp-42\nexp-42/*.png", text=True, capture_output=True, timeout=5, env={"PATH": "/usr/bin:/bin"},
    )
    stop.set()
    thread.join(timeout=5)

    sent = [request for request in requests if request["action"] != "ping"]
    if not capable:
        assert result.returncode == 1
        assert "cannot download folders" in result.stderr
        assert sent == []
        return
    assert result.returncode == 0, result.stderr
    for request in sent:
        request.pop("host_info")
    assert sent == [
        {"version": 1, "action": "download_folder", "path": str(folder), "ssh_host": "devbox",
         "ask_destination": False, "size_bytes": 8, "file_count": 2},
        {"version": 1, "action": "download_folder", "path": str(folder), "ssh_host": "devbox",
         "ask_destination": False, "files": ["a.png", "link.png"], "size_bytes": 5, "file_count": 1},
    ]
