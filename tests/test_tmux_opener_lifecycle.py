from __future__ import annotations

import runpy
import socket
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def client_module():
    return runpy.run_path(str(ROOT / "bin" / "tmux-opener-client"))


def test_live_owner_cannot_be_replaced(tmp_path: Path) -> None:
    client = client_module()
    path = tmp_path / "client.sock"
    server = client["bind_server"](str(path))
    identity = path.stat().st_ino
    try:
        with pytest.raises(BlockingIOError):
            client["bind_server"](str(path))
        assert path.stat().st_ino == identity
        with socket.socket(socket.AF_UNIX) as peer:
            peer.connect(str(path))
    finally:
        server.cleanup()


def test_old_owner_cleanup_preserves_replacement(tmp_path: Path) -> None:
    client = client_module()
    path = tmp_path / "client.sock"
    server = client["bind_server"](str(path))
    path.unlink()
    with socket.socket(socket.AF_UNIX) as replacement:
        replacement.bind(str(path))
        identity = path.stat().st_ino
        server.cleanup()
        assert path.stat().st_ino == identity


@pytest.mark.parametrize("symlink", [False, True])
def test_non_socket_is_never_removed(tmp_path: Path, symlink: bool) -> None:
    client = client_module()
    path = tmp_path / "client.sock"
    target = tmp_path / "important"
    target.write_text("preserve")
    if symlink:
        path.symlink_to(target)
    else:
        path.write_text("preserve")
    with pytest.raises(RuntimeError):
        client["bind_server"](str(path))
    assert path.read_text() == "preserve"
    assert target.read_text() == "preserve"


def test_legacy_listener_is_not_unlinked(tmp_path: Path) -> None:
    client = client_module()
    path = tmp_path / "client.sock"
    with socket.socket(socket.AF_UNIX) as legacy:
        legacy.bind(str(path))
        legacy.listen()
        identity = path.stat().st_ino
        with pytest.raises(RuntimeError):
            client["bind_server"](str(path))
        assert path.stat().st_ino == identity


def test_stale_socket_can_be_reclaimed(tmp_path: Path) -> None:
    client = client_module()
    path = tmp_path / "client.sock"
    with socket.socket(socket.AF_UNIX) as stale:
        stale.bind(str(path))
    server = client["bind_server"](str(path))
    try:
        with socket.socket(socket.AF_UNIX) as peer:
            peer.connect(str(path))
    finally:
        server.cleanup()
    assert not path.exists()
