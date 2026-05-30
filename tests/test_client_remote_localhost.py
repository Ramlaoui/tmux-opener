from __future__ import annotations

import io
import runpy
from argparse import Namespace
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENT_PATH = REPO_ROOT / "bin" / "tmux-opener-client"
FAKE_SSH = "/usr/bin/ssh"
FAKE_OPENER = "xdg-open"


def load_client(monkeypatch: Any) -> dict[str, Any]:
    client = runpy.run_path(str(CLIENT_PATH))
    monkeypatch.setattr(client["platform"], "system", lambda: "Linux")
    monkeypatch.setattr(
        client["shutil"],
        "which",
        lambda name: {"ssh": FAKE_SSH}.get(name),
    )
    monkeypatch.setitem(
        client["allocate_localhost_forward_port"].__globals__,
        "port_available",
        lambda _port: True,
    )
    return client


def args(**overrides: object) -> Namespace:
    values = {
        "dry_run": True,
        "verbose": False,
        "localhost_forward_start_port": 18000,
        "localhost_forward_end_port": 18999,
    }
    values.update(overrides)
    return Namespace(**values)


def request(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "version": 1,
        "action": "open_remote_localhost",
        "ssh_host": "devbox",
        "scheme": "http",
        "remote_host": "localhost",
        "remote_port": 8080,
        "path": "/docs",
        "query": "token=abc",
        "fragment": "install",
    }
    values.update(overrides)
    return values


def test_remote_localhost_dry_run_starts_tunnel_and_opens_rewritten_url(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    client = load_client(monkeypatch)

    client["open_remote_localhost"](request(), {"devbox"}, args())

    output = capsys.readouterr().out
    assert (
        f"dry-run tunnel: {FAKE_SSH} -N -S none -o ExitOnForwardFailure=no "
        "-o ForkAfterAuthentication=no "
        "-L 127.0.0.1:18080:localhost:8080 devbox"
    ) in output
    assert f"dry-run: {FAKE_OPENER} 'http://127.0.0.1:18080/docs?token=abc#install'" in output


def test_remote_localhost_uses_first_free_port_when_preferred_is_taken(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    client = load_client(monkeypatch)
    monkeypatch.setitem(
        client["allocate_localhost_forward_port"].__globals__,
        "port_available",
        lambda port: port != 18080,
    )

    client["open_remote_localhost"](request(), {"devbox"}, args())

    output = capsys.readouterr().out
    assert "-L 127.0.0.1:18000:localhost:8080 devbox" in output
    assert f"dry-run: {FAKE_OPENER} 'http://127.0.0.1:18000/docs?token=abc#install'" in output


def test_remote_localhost_rejects_tunnel_that_never_listens(monkeypatch: Any) -> None:
    client = load_client(monkeypatch)

    class FakeProcess:
        terminated = False

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            self.terminated = True

        def wait(self, timeout: float | None = None) -> int:
            return 0

        def kill(self) -> None:
            pass

    process = FakeProcess()
    stderr_log = io.BytesIO(b"remote forward already exists")
    monkeypatch.setattr(client["subprocess"], "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(client["tempfile"], "TemporaryFile", lambda: stderr_log)
    monkeypatch.setitem(client["ensure_remote_localhost_forward"].__globals__, "localhost_port_ready", lambda _port: False)
    monkeypatch.setitem(client["ensure_remote_localhost_forward"].__globals__, "LOCALHOST_FORWARD_STARTUP_TIMEOUT", 0)

    with pytest.raises(client["RequestError"], match="localhost forward did not listen"):
        client["open_remote_localhost"](request(), {"devbox"}, args(dry_run=False))

    assert process.terminated


def test_remote_localhost_rejects_unallowed_ssh_host(monkeypatch: Any) -> None:
    client = load_client(monkeypatch)

    with pytest.raises(client["RequestError"], match="ssh_host is not allowed"):
        client["open_remote_localhost"](request(), {"other"}, args())


def test_remote_localhost_rejects_unknown_remote_host(monkeypatch: Any) -> None:
    client = load_client(monkeypatch)

    with pytest.raises(client["RequestError"], match="unsupported remote localhost host"):
        client["open_remote_localhost"](request(remote_host="example.com"), {"devbox"}, args())
