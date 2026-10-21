from __future__ import annotations

import json
import os
import runpy
import socket
import sys
import threading
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import tmux_opener_common as common  # noqa: E402


DESKTOP = {"DISPLAY": ":0", "XDG_RUNTIME_DIR": "/run/user/1000"}


def process(proc: Path, pid: int, comm: str, ppid: int, environ: dict[str, str] | None = None) -> None:
    (proc / str(pid)).mkdir(parents=True)
    (proc / str(pid) / "stat").write_text(f"{pid} ({comm}) S {ppid} {pid} {pid} 0 -1\n")
    if environ is not None:
        (proc / str(pid) / "environ").write_text("".join(f"{key}={value}\0" for key, value in environ.items()))


@pytest.fixture
def proc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(common, "PROC_ROOT", tmp_path / "proc")
    monkeypatch.setenv("TMUX_OPENER_CLIENT_PID", "40")
    return tmp_path / "proc"


def test_client_at_the_host_desktop_returns_its_display(proc: Path) -> None:
    process(proc, 40, "tmux: client", 30, {**DESKTOP, "WAYLAND_DISPLAY": "wayland-1", "TERM": "alacritty"})
    process(proc, 30, "bash", 20)
    process(proc, 20, "alacritty (x)", 1)
    assert common.client_display_env() == {**DESKTOP, "WAYLAND_DISPLAY": "wayland-1"}


@pytest.mark.parametrize("comm, environ", [
    ("sshd-session", DESKTOP),  # su or sudo dropped SSH_CONNECTION
    ("sshd", DESKTOP),
    ("bash", {**DESKTOP, "SSH_CONNECTION": "192.0.2.1 5000 192.0.2.2 22"}),
    ("bash", {"DISPLAY": "localhost:10.0"}),  # X11 forwarding
    ("mosh-server", {"TERM": "xterm"}),
])
def test_remote_or_unproven_clients_keep_the_bridge(proc: Path, comm: str, environ: dict[str, str]) -> None:
    process(proc, 40, "tmux: client", 30, environ)
    process(proc, 30, comm, 1)
    assert common.client_display_env() is None


@pytest.mark.parametrize("pid", ["", "abc", "41"])
def test_unknown_client_keeps_the_bridge(proc: Path, monkeypatch: pytest.MonkeyPatch, pid: str) -> None:
    monkeypatch.setenv("TMUX_OPENER_CLIENT_PID", pid)
    process(proc, 40, "tmux: client", 1, DESKTOP)
    assert common.client_display_env() is None


@pytest.fixture
def bridge(tmp_path: Path):
    path = tmp_path / "bridge.sock"
    requests: list[dict[str, object]] = []
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen()
    server.settimeout(0.2)
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                connection, _ = server.accept()
            except OSError:
                continue
            with connection:
                requests.append(json.loads(connection.recv(65536)))
                connection.sendall(b'{"version":1,"ok":true,"client":"tmux-opener-client"}\n')

    thread = threading.Thread(target=serve)
    thread.start()
    yield path, requests
    stop.set()
    thread.join()
    server.close()


@pytest.fixture
def dispatch(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    saved = dict(os.environ)
    # The tmux server was started over SSH, then the session took another client's display.
    monkeypatch.setenv("DISPLAY", "localhost:10.0")
    monkeypatch.setenv("WAYLAND_DISPLAY", "stale")
    monkeypatch.delenv("TMUX", raising=False)

    def run(*args: str) -> tuple[int, str]:
        monkeypatch.setattr(sys, "argv", ["tmux-opener-dispatch", *args, "--no-log", "--route-feedback", "never"])
        with pytest.raises(SystemExit) as exit_info:
            runpy.run_path(str(ROOT / "scripts/tmux-opener-dispatch"), run_name="__main__")
        return exit_info.value.code, capsys.readouterr().err

    yield run
    os.environ.clear()
    os.environ.update(saved)


def test_desktop_client_opens_on_its_own_display(proc: Path, bridge, dispatch, tmp_path: Path) -> None:
    socket_path, requests = bridge
    process(proc, 40, "tmux: client", 1, DESKTOP)
    seen = tmp_path / "seen"
    code, _ = dispatch("https://example.com", "--socket", str(socket_path), "--fallback-command",
                       f'printf "%s %s" "$DISPLAY" "${{WAYLAND_DISPLAY-unset}}" > {seen}')
    assert code == 0
    assert seen.read_text() == ":0 unset"
    assert requests == []


def test_ssh_client_still_uses_the_bridge(proc: Path, bridge, dispatch, tmp_path: Path) -> None:
    socket_path, requests = bridge
    process(proc, 40, "tmux: client", 30, {"SSH_CONNECTION": "192.0.2.1 5000 192.0.2.2 22"})
    process(proc, 30, "sshd-session", 1)
    code, _ = dispatch("https://example.com", "--socket", str(socket_path), "--fallback-command", "exit 42")
    assert code == 0
    assert [request["action"] for request in requests] == ["ping", "open_url"]


def test_desktop_client_downloads_explain_why_not(proc: Path, bridge, dispatch, tmp_path: Path) -> None:
    socket_path, requests = bridge
    process(proc, 40, "tmux: client", 1, DESKTOP)
    (tmp_path / "result.txt").touch()
    code, err = dispatch(str(tmp_path / "result.txt"), "--download", "--socket", str(socket_path))
    assert code == 1
    assert "this tmux client is on the host's own desktop" in err
    assert requests == []
