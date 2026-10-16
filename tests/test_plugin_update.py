from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import tmux_opener_dashboard as desktop
from test_desktop_dashboard import _http, _start_server, _stop_server
from test_host_dashboard import FakeScreen, dashboard, status_response


REPO_ROOT = Path(__file__).resolve().parents[1]
UPDATE_SCRIPT = REPO_ROOT / "scripts" / "tmux-opener-update"


def _git(*args: object, cwd: Path) -> str:
    return subprocess.run(["git", *map(str, args)], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def plugin_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """A TPM-style plugin checkout behind its origin, with a fake tmux on PATH."""

    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    home = tmp_path / "home"
    origin = tmp_path / "origin"
    origin.mkdir(parents=True)
    log = tmp_path / "tmux.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "tmux").write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> {log}\n')
    (bin_dir / "tmux").chmod(0o755)
    for key, value in {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
                       "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
                       "GIT_COMMITTER_EMAIL": "t@example.invalid"}.items():
        monkeypatch.setenv(key, value)
    env = {**os.environ, "HOME": str(home), "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    env.pop("TMUX", None)
    env.pop("XDG_CONFIG_HOME", None)

    (origin / "tmux-opener.tmux").write_text('#!/bin/sh\ntmux bind-key reloaded\n')
    (origin / "tmux-opener.tmux").chmod(0o755)
    (origin / "scripts").mkdir()
    shutil.copy2(UPDATE_SCRIPT, origin / "scripts" / "tmux-opener-update")
    _git("init", "-q", "-b", "main", cwd=origin)
    _git("add", ".", cwd=origin)
    _git("commit", "-qm", "first", cwd=origin)
    checkout = home / ".tmux" / "plugins" / "tmux-opener"
    checkout.parent.mkdir(parents=True)
    _git("clone", "-q", origin, checkout, cwd=tmp_path)
    (origin / "NEW").write_text("new\n")
    _git("add", ".", cwd=origin)
    _git("commit", "-qm", "second", cwd=origin)
    return {"env": env, "origin": origin, "checkout": checkout, "log": log}


def test_piped_update_finds_the_tpm_checkout_fast_forwards_and_reloads(plugin_host) -> None:
    env, checkout, origin = plugin_host["env"], plugin_host["checkout"], plugin_host["origin"]
    before = _git("rev-parse", "--short", "HEAD", cwd=checkout)
    after = _git("rev-parse", "--short", "HEAD", cwd=origin)

    # Desktop dashboards pipe the script, so $0 does not point into the plugin.
    result = subprocess.run(["sh", "-s"], input=UPDATE_SCRIPT.read_text(), env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith(f"updated {before} -> {after}; bindings reloaded")
    assert (checkout / "NEW").exists()
    assert "bind-key reloaded" in plugin_host["log"].read_text()

    again = subprocess.run([checkout / "scripts" / "tmux-opener-update"], env=env, capture_output=True, text=True)
    assert again.returncode == 0 and f"is up to date ({after})" in again.stdout


def test_update_refuses_installs_it_cannot_fast_forward(plugin_host) -> None:
    env, checkout = plugin_host["env"], plugin_host["checkout"]
    shutil.rmtree(checkout / ".git")
    result = subprocess.run(["sh", "-s"], input=UPDATE_SCRIPT.read_text(), env=env, capture_output=True, text=True)
    assert result.returncode == 1 and "is not a git checkout" in result.stdout

    shutil.rmtree(checkout)
    result = subprocess.run(["sh", "-s"], input=UPDATE_SCRIPT.read_text(), env=env, capture_output=True, text=True)
    assert result.returncode == 1 and "plugin not found" in result.stdout


def _bridge_dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    state, snippets = tmp_path / "state", tmp_path / "snippets"
    state.mkdir(exist_ok=True)
    snippets.mkdir(exist_ok=True)
    (snippets / "box.conf").write_text("Host box\n")
    return tmp_path / "ssh_config", state, snippets


def _fake_ssh(tmp_path: Path, body: str) -> Path:
    ssh = tmp_path / "fake-ssh"
    ssh.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > {tmp_path}/argv\ncat > {tmp_path}/stdin\n{body}\n')
    ssh.chmod(0o755)
    return ssh


def test_desktop_update_pipes_this_install_script_to_a_bridged_host(tmp_path: Path) -> None:
    config, state, snippets = _bridge_dirs(tmp_path)
    ssh = _fake_ssh(tmp_path, 'printf "noise\\ntmux-opener on box updated a -> b; bindings reloaded\\n"')

    assert desktop.update_plugin("elsewhere", config, state, snippets, ssh=str(ssh))["ok"] is False
    assert desktop.update_plugin("-oProxyCommand=x", config, state, snippets, ssh=str(ssh))["ok"] is False
    assert not (tmp_path / "argv").exists()

    response = desktop.update_plugin("box", config, state, snippets, ssh=str(ssh))
    assert response == {"ok": True, "host": "box", "message": "tmux-opener on box updated a -> b; bindings reloaded"}
    argv = (tmp_path / "argv").read_text().splitlines()
    assert argv[-3:] == ["--", "box", "sh -s"]
    assert ["-F", str(config)] == argv[:2]
    assert {"BatchMode=yes", "ClearAllForwardings=yes", "ControlMaster=no"} <= set(argv)
    assert (tmp_path / "stdin").read_bytes() == UPDATE_SCRIPT.read_bytes()

    failing = _fake_ssh(tmp_path, 'printf "box: Permission denied (publickey).\\033[2J\\n" >&2; exit 255')
    assert desktop.update_plugin("box", config, state, snippets, ssh=str(failing)) == {
        "ok": False, "error": "box: Permission denied (publickey).[2J"}


def test_status_marks_only_bridged_hosts_updatable(tmp_path: Path) -> None:
    _config, state, snippets = _bridge_dirs(tmp_path)
    clients = desktop.collect_status(state, snippets)["clients"]
    assert [(client["host"], client["can_update"]) for client in clients] == [("box", True)]
    assert desktop.collect_status(state, snippets, host="other")["clients"][0]["can_update"] is False


def test_plugin_update_api_requires_the_owner_and_a_bridged_host(tmp_path: Path, monkeypatch) -> None:
    server, thread = _start_server(tmp_path)
    (server.snippet_dir / "box.conf").write_text("Host box\n")
    calls = []
    monkeypatch.setattr(desktop, "update_plugin", lambda host, *args: calls.append((host, *args)) or {"ok": True, "message": "done"})
    port = server.server_address[1]
    headers = {"Authorization": "Bearer test-token", "Origin": f"http://127.0.0.1:{port}",
               "Content-Type": "application/json"}

    def post(payload, selected_headers=None):
        status, _, body = _http(server, "POST", "/api/plugin-update", headers if selected_headers is None else selected_headers,
                                json.dumps(payload).encode())
        return status, body

    try:
        assert post({"host": "box"}, {})[0] == 401
        assert post({"host": "box"}, {**headers, "Origin": "https://untrusted.invalid"})[0] == 403
        assert post({"host": "box", "branch": "main"})[0] == 400
        assert post({"host": "other"})[0] == 403
        assert calls == []
        status, body = post({"host": "box"})
        assert (status, json.loads(body)) == (200, {"ok": True, "message": "done"})
        assert calls == [("box", server.ssh_config, server.state_dir, server.snippet_dir)]
    finally:
        _stop_server(server, thread)


def test_tmux_dashboards_update_the_selected_host_or_their_own(monkeypatch) -> None:
    entries = [{"host": "box", "socket": "/tmp/box.sock", "online": False, "can_restart": False,
                "can_update": True, "client_info": {}}]
    calls = []

    def update(client, *, local, **_paths):
        calls.append((client["host"], local))
        return f"tmux-opener on {client['host']} updated a -> b; bindings reloaded"

    monkeypatch.setattr(dashboard, "request_plugin_update", update)
    monkeypatch.setattr(dashboard, "request_local_status", lambda *args, **kwargs: {**status_response(), "clients": entries})
    screen = FakeScreen(height=24, width=100, keys=[9, ord("u"), ord("q")])
    dashboard.run_live_dashboard(screen, socket_path=None, cwd="/tmp", pane=None, ssh_host=None, timeout=1, local=True)
    text = "\n".join(row for frame in screen.frames for row in frame)
    assert "updating tmux-opener on box…" in text and "box updated a -> b; bindings reloaded" in text
    assert "u update plugin" in text

    monkeypatch.setattr(dashboard, "request_status", lambda *args, **kwargs: status_response())
    remote = FakeScreen(height=24, width=100, keys=[9, ord("u"), ord("q")])
    dashboard.run_live_dashboard(remote, socket_path="/tmp/remote.sock", cwd="/tmp", pane=None, ssh_host=None, timeout=1)
    assert calls == [("box", True), ("cluster", False)]
    assert "updating tmux-opener on this host…" in "\n".join(row for frame in remote.frames for row in frame)


def test_desktop_tmux_dashboard_needs_a_bridge_to_update() -> None:
    with pytest.raises(dashboard.StatusError, match="has no bridge"):
        dashboard.request_plugin_update({"host": "loose", "can_update": False}, local=True, ssh_config="~/.ssh/config",
                                        state_dir="/tmp", snippet_dir="/tmp")
