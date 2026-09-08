from __future__ import annotations

import json
import runpy
import socket
import subprocess
import sys
import tempfile
import threading
import time
from argparse import Namespace
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


CLIENT_PATH = Path(__file__).resolve().parents[1] / "bin" / "tmux-opener-client"
PING = b'{"version":1,"action":"ping"}\n'


def connect(path: str) -> socket.socket:
    peer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    peer.settimeout(1)
    peer.connect(path)
    return peer


def exchange(path: str, payload: bytes) -> dict[str, object]:
    with connect(path) as peer:
        peer.sendall(payload)
        with peer.makefile("rb") as response:
            return json.loads(response.readline())


@contextmanager
def running_client(*, once: bool = False) -> Iterator[tuple[subprocess.Popen[bytes], str, Path]]:
    # Keep Unix socket names below macOS's small sockaddr_un path limit.
    with tempfile.TemporaryDirectory(prefix="opener-test-", dir="/tmp") as directory:
        path = str(Path(directory) / "client.sock")
        log_path = Path(directory) / "client.log"
        with log_path.open("wb") as log:
            process = subprocess.Popen(
                [sys.executable, str(CLIENT_PATH), "--socket", path, "--dry-run", *(["--once"] if once else [])],
                stdout=log,
                stderr=log,
            )
            try:
                deadline = time.monotonic() + 5
                while "listening on" not in log_path.read_text():
                    assert process.poll() is None, log_path.read_text()
                    assert time.monotonic() < deadline, "client did not start"
                    time.sleep(0.01)
                yield process, path, log_path
            finally:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
                    raise


def test_partial_peer_does_not_starve_ping_or_extend_request_deadline() -> None:
    with running_client() as (_process, path, _log), connect(path) as partial:
        partial.sendall(b'{"version":')
        assert exchange(path, PING)["ok"] is True
        partial.settimeout(0.1)
        deadline = time.monotonic() + 3
        response = b""
        while b"\n" not in response:
            assert time.monotonic() < deadline, "trickled bytes extended the request deadline"
            try:
                partial.sendall(b" ")
            except BrokenPipeError:
                pass
            try:
                response += partial.recv(65536)
            except socket.timeout:
                pass
        assert json.loads(response)["ok"] is False
        assert exchange(path, PING)["version"] == 1


def test_invalid_frames_and_disconnected_peers_leave_listener_healthy() -> None:
    with running_client() as (process, path, _log):
        for payload in (b"\xff\n", b"{not-json}\n", b"[]\n", b'{"version":' + b"9" * 5000 + b"}\n"):
            assert exchange(path, payload)["ok"] is False
        for payload in (b"", PING, b'{"version":1,"action":"open_url","url":"https://example.test"}\n'):
            with connect(path) as peer:
                if payload:
                    peer.sendall(payload)
        response = exchange(path, PING)
        assert response["client"] == "tmux-opener-client"
        assert response["pid"] == process.pid


def test_normal_success_and_rejection_logs_exclude_payload_secrets() -> None:
    with running_client() as (_process, path, log):
        secret = "private-path-token-should-not-be-logged"
        request = {"version": 1, "action": "open_url", "url": f"https://example.test/{secret}?token={secret}"}
        assert exchange(path, json.dumps(request).encode() + b"\n")["ok"] is True
        request = {"version": 1, "action": secret}
        assert exchange(path, json.dumps(request).encode() + b"\n")["ok"] is False
        request = {"version": 1, "action": "open_url", "url": "https://example.test/\ud800"}
        assert exchange(path, json.dumps(request).encode() + b"\n")["ok"] is False
        assert secret not in log.read_text()
        assert exchange(path, PING)["ok"] is True


def test_once_returns_acknowledgement_before_exiting() -> None:
    with running_client(once=True) as (process, path, _log):
        assert exchange(path, PING)["ok"] is True
        assert process.wait(timeout=3) == 0


def test_slow_dispatch_keeps_ping_responsive_and_shutdown_discards_queue(monkeypatch: Any) -> None:
    client = runpy.run_path(str(CLIENT_PATH))
    entered = threading.Event()
    release = threading.Event()
    stop = threading.Event()
    actions: list[object] = []
    failures: list[BaseException] = []

    def slow_dispatch(request: dict[str, object], _args: Namespace) -> None:
        actions.append(request["action"])
        entered.set()
        assert release.wait(timeout=5)

    monkeypatch.setitem(client["serve"].__globals__, "dispatch", slow_dispatch)
    args = Namespace(once=False, default_ssh_host=None, allow_ssh_host=[], allow_any_ssh_host=False)
    with tempfile.TemporaryDirectory(prefix="opener-test-", dir="/tmp") as directory:
        path = str(Path(directory) / "client.sock")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(path)
            server.listen(16)

            def run() -> None:
                try:
                    client["serve"](server, args, stop)
                except BaseException as exc:
                    failures.append(exc)

            worker = threading.Thread(target=run)
            worker.start()
            try:
                with connect(path) as first, connect(path) as queued:
                    first.sendall(b'{"version":1,"action":"first"}\n')
                    assert entered.wait(timeout=1)
                    queued.sendall(b'{"version":1,"action":"queued"}\n')
                    assert exchange(path, PING)["ok"] is True
                    # The queued request occupies the one waiting dispatch slot.
                    assert exchange(path, b'{"version":1,"action":"overflow"}\n')["ok"] is False
                    stop.set()
                    release.set()
                    worker.join(timeout=1)
                    assert not worker.is_alive()
                    assert actions == ["first"]
                    assert not failures
            finally:
                stop.set()
                release.set()
                worker.join(timeout=2)
