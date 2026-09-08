from __future__ import annotations

import socket
import sys
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tmux_opener_common import bridge_available, send_request  # noqa: E402


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
