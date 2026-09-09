from __future__ import annotations

import json
import runpy
import socket
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tmux_opener_common import bridge_available, deliver_request, send_request  # noqa: E402


@contextmanager
def responder(chunks: list[bytes]):
    # Keep AF_UNIX paths below macOS's limit, independent of pytest's root.
    with tempfile.TemporaryDirectory(prefix="opener-ack-", dir="/tmp") as directory:
        path = str(Path(directory) / "s")
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(path)
            listener.listen(1)
            listener.settimeout(2)

            def serve():
                with listener.accept()[0] as peer:
                    peer.settimeout(2)
                    peer.recv(65536)
                    for chunk in chunks:
                        peer.sendall(chunk)

            worker = threading.Thread(target=serve)
            worker.start()
            try:
                yield path
            finally:
                worker.join(timeout=3)
                assert not worker.is_alive()


def test_fragmented_acknowledgement_is_accepted():
    with responder([b'{"ok":' + b" " * 65536, b'true}\n']) as path:
        assert send_request(path, {"version": 1, "action": "ping"}, 1) == {"ok": True}

@pytest.mark.parametrize("reply", [b"", b'{"ok":true}', b'{"ok":"yes"}\n', b'[]\n', b'\xff\n'])
def test_missing_or_invalid_acknowledgement_is_not_success(reply):
    with responder([reply]) as path:
        with pytest.raises((OSError, ValueError)):
            send_request(path, {"version": 1, "action": "ping"}, 1)


def test_health_requires_opener_identity():
    with responder([b'{"ok":true}\n']) as path:
        assert not bridge_available(path, 1)
    with responder([b'{"ok":true,"client":"tmux-opener-client","version":1}\n']) as path:
        assert bridge_available(path, 1)


@pytest.mark.parametrize("accepted", [True, False])
def test_delivery_log_excludes_request_and_response_secrets(tmp_path, accepted):
    secret = "synthetic-private-target"
    request = {"version": 1, "action": "open_url", "url": f"https://example.test/?token={secret}"}
    reply = json.dumps({"ok": accepted, "error": secret}).encode() + b"\n"
    log = tmp_path / "sender.log"
    with responder([reply]) as path:
        assert deliver_request(path, request, 1, str(log), "none") == (0 if accepted else 1)
    assert secret not in log.read_text()
    assert log.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("consumer", ["local-health", "remote-dispatch"])
def test_delayed_healthy_client_is_not_treated_as_unavailable(consumer):
    root = Path(__file__).resolve().parents[1]
    requests = []
    stopping = threading.Event()
    with tempfile.TemporaryDirectory(prefix="opener-cold-", dir="/tmp") as directory:
        path = str(Path(directory) / "s")
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(path)
            listener.listen(2)
            listener.settimeout(0.1)

            def serve():
                while not stopping.is_set():
                    try:
                        peer, _ = listener.accept()
                    except TimeoutError:
                        continue
                    with peer:
                        peer.settimeout(2)
                        request = json.loads(peer.recv(65536))
                        requests.append(request["action"])
                        if request["action"] == "ping":
                            # Model delayed scheduling, not a dead process.
                            if stopping.wait(1.2):
                                return
                            reply = {"ok": True, "client": "tmux-opener-client", "version": 1}
                        else:
                            reply = {"ok": True}
                        try:
                            peer.sendall(json.dumps(reply).encode() + b"\n")
                        except OSError:
                            return

            worker = threading.Thread(target=serve)
            worker.start()
            try:
                if consumer == "local-health":
                    wrapper = runpy.run_path(str(root / "bin" / "tmux-opener"))
                    response, error = wrapper["client_ping_response"](Path(path))
                    assert error is None
                    assert response["ok"] is True
                    assert requests == ["ping"]
                else:
                    result = subprocess.run([
                        sys.executable, str(root / "scripts" / "tmux-opener-dispatch"),
                        "--socket", path, "--timeout", "3", "--fallback", "none",
                        "--route-feedback", "never", "--no-log", "https://example.test/",
                    ], capture_output=True, text=True, timeout=5)
                    assert result.returncode == 0, result.stderr
                    assert requests == ["ping", "open_url"]
            finally:
                stopping.set()
                worker.join(timeout=3)
                assert not worker.is_alive()
