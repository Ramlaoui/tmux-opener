from __future__ import annotations

import curses
import importlib.util
from importlib.machinery import SourceFileLoader
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "tmux-opener-status"
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def load_dashboard():
    loader = SourceFileLoader("tmux_opener_status", str(SCRIPT))
    spec = importlib.util.spec_from_loader("tmux_opener_status", loader)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


dashboard = load_dashboard()


def test_viewer_keyboard_selection_skips_uninstalled_apps():
    settings = {"rules": [], "pdf_viewer": "auto"}
    changed, _selected = dashboard.edit_settings(settings, 2, curses.KEY_RIGHT, None,
                                                 ["auto", "sioyek", "acrobat", "system"])
    assert changed and settings["pdf_viewer"] == "sioyek"


def status_response() -> dict[str, object]:
    return {
        "ok": True,
        "version": 1,
        "client_info": {
            "hostname": "laptop",
            "user": "alice",
            "os": "Linux",
            "pid": 123,
            "default_ssh_host": "cluster",
            "started_at": "2026-10-10T10:00:00+00:00",
            "last_request_at": "2026-10-10T10:01:00+00:00",
        },
        "hosts": [
            {
                "ssh_host": "cluster",
                "hostname": "compute-01",
                "user": "remote",
                "os": "Linux",
                "cwd": "/scratch/project",
                "pane": "%42",
                "last_seen": "2026-10-10T10:01:00+00:00",
            }
        ],
        "downloads": [
            {
                "id": "download-1",
                "ssh_host": "cluster",
                "path": "/scratch/result\x1b[31m.csv",
                "destination": "/home/alice/Downloads/result.csv",
                "state": "downloading",
                "bytes_received": 512,
                "size_bytes": 1024,
                "created_at": "2026-10-10T10:00:00+00:00",
                "updated_at": "2026-10-10T10:01:00+00:00",
                "error": "",
                "ask_destination": False,
            }
        ],
        "remote_localhost_forwards": [],
    }


def unix_server(replies: list[dict[str, object]], requests: list[dict[str, object]]):
    directory = tempfile.TemporaryDirectory(prefix="tmux-opener-status-", dir="/tmp")
    path = str(Path(directory.name) / "status.sock")
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(path)
    listener.listen(len(replies) + 2)
    listener.settimeout(3)

    def serve() -> None:
        try:
            for reply in replies:
                peer, _ = listener.accept()
                with peer:
                    data = peer.recv(1024 * 1024)
                    requests.append(json.loads(data.split(b"\n", 1)[0]))
                    peer.sendall(json.dumps(reply).encode() + b"\n")
        finally:
            listener.close()

    worker = threading.Thread(target=serve)
    worker.start()
    return directory, path, worker


def test_status_request_contains_self_reported_host_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMUX_PANE", "%7")
    monkeypatch.setattr(dashboard.platform, "node", lambda: "remote-node")
    monkeypatch.setattr(dashboard.platform, "system", lambda: "TestOS")
    monkeypatch.setattr(dashboard.getpass, "getuser", lambda: "test-user")

    request = dashboard.build_status_request("/tmp/work", ssh_host="cluster")

    assert request == {
        "version": 1,
        "action": "get_status",
        "ssh_host": "cluster",
        "host_info": {
            "hostname": "remote-node",
            "user": "test-user",
            "os": "TestOS",
            "cwd": "/tmp/work",
            "pane": "%7",
        },
    }


def test_status_response_and_json_snapshot_are_supported() -> None:
    requests: list[dict[str, object]] = []
    directory, path, worker = unix_server([status_response()], requests)
    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, "--json", "--socket", path, "--cwd", "/tmp/work", "--pane", "%9"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        worker.join(timeout=3)
        directory.cleanup()
    assert result.returncode == 0, result.stderr
    parsed = json.loads(result.stdout)
    assert parsed["client_info"]["hostname"] == "laptop"
    assert requests[0]["action"] == "get_status"
    assert requests[0]["host_info"]["cwd"] == "/tmp/work"
    assert requests[0]["host_info"]["pane"] == "%9"


def test_old_client_is_explicitly_reported_in_json() -> None:
    requests: list[dict[str, object]] = []
    directory, path, worker = unix_server([{"ok": True}], requests)
    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, "--json", "--socket", path],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        worker.join(timeout=3)
        directory.cleanup()
    assert result.returncode == 1
    assert json.loads(result.stdout) == {"error": "old client unsupported: get_status is unavailable", "ok": False}


def test_rendering_sanitizes_terminal_controls_and_shows_recent_host_label() -> None:
    lines = dashboard.render_snapshot_lines(status_response())
    rendered = "\n".join(lines)
    assert "\\x1b" not in rendered
    assert "\x1b" not in rendered
    assert "does not indicate active SSH" in rendered
    assert "512 B of 1.0 KiB (50%)" in rendered
    assert "compute-01" in rendered
    assert "result[31m.csv" in rendered
    assert "source  cluster:/scratch/result[31m.csv" in rendered
    assert "TRANSFERS  1 active" in rendered
    assert "resumed at" not in rendered


def test_detail_block_shows_where_a_transfer_resumed() -> None:
    snapshot = status_response()
    snapshot["downloads"][0]["resumed_from"] = 256
    rendered = "\n".join(dashboard.render_snapshot_lines(snapshot))
    assert "resumed at 256 B" in rendered


def test_action_requests_use_the_same_socket_and_download_id() -> None:
    requests: list[dict[str, object]] = []
    directory, path, worker = unix_server([{"ok": True}, {"ok": True}], requests)
    try:
        dashboard.request_action(path, "cancel_download", "download-1", 0.75)
        dashboard.request_action(path, "retry_download", "download-1", 0.75)
    finally:
        worker.join(timeout=3)
        directory.cleanup()
    assert requests == [
        {"version": 1, "action": "cancel_download", "download_id": "download-1"},
        {"version": 1, "action": "retry_download", "download_id": "download-1"},
    ]


def test_action_request_includes_optional_host_scope() -> None:
    assert dashboard.build_action_request("cancel_download", "download-1", "cluster") == {
        "version": 1,
        "action": "cancel_download",
        "download_id": "download-1",
        "ssh_host": "cluster",
    }


def test_local_status_aggregates_clients_and_routes_download_actions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    requests: list[tuple[Path, dict[str, object], float]] = []
    raw = {
        "updated_at": "now",
        "clients": [
            {
                "host": "cluster",
                "socket": str(tmp_path / "cluster.sock"),
                "online": True,
                "client_info": {"hostname": "desktop", "user": "alice", "os": "Linux", "pid": 7},
                "hosts": [{"ssh_host": "cluster", "hostname": "compute", "user": "remote", "os": "Linux", "cwd": "/work", "last_seen": "now"}],
                "downloads": [{"id": "dl-1", "ssh_host": "cluster", "path": "/work/result.xyz", "state": "failed", "error": "bad"}],
                "remote_localhost_forwards": [{"host": "cluster", "port": 8080}],
            },
            {"host": "offline", "socket": str(tmp_path / "offline.sock"), "online": False, "error": "unavailable", "client_info": {}, "hosts": [], "downloads": [], "remote_localhost_forwards": []},
        ],
    }

    def fake_client(path: Path, request: dict[str, object], timeout: float) -> dict[str, object]:
        requests.append((path, request, timeout))
        return {"ok": True}

    monkeypatch.setattr(dashboard, "_local_dashboard_api", lambda: (fake_client, lambda *_args, **_kwargs: raw))
    snapshot = dashboard.request_local_status(tmp_path / "state", tmp_path / "snippets")

    assert snapshot["selected_client"] == "cluster"
    assert snapshot["client_info"]["hostname"] == "desktop"
    assert snapshot["hosts"][0]["hostname"] == "compute"
    assert snapshot["downloads"][0]["_socket"] == str(tmp_path / "cluster.sock")
    assert snapshot["remote_localhost_forwards"] == [{"host": "cluster", "port": 8080}]
    assert "desktop dashboard" in "\n".join(dashboard.render_snapshot_lines(snapshot, ssh_host="cluster", pane="%7"))

    dashboard.request_local_action(snapshot["downloads"][0], "cancel_download", 0.75)
    assert requests == [
        (
            tmp_path / "cluster.sock",
            {"version": 1, "action": "cancel_download", "download_id": "dl-1", "ssh_host": "cluster"},
            0.75,
        )
    ]


def test_interactive_remote_failure_falls_back_to_desktop_cli_without_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fail_status(*_args, **_kwargs):
        raise OSError("forward unavailable")

    class Result:
        returncode = 17

    monkeypatch.setattr(dashboard, "request_status", fail_status)
    monkeypatch.setattr(dashboard.shutil, "which", lambda name: "/usr/local/bin/tmux-opener" if name == "tmux-opener" else None)
    monkeypatch.setattr(dashboard.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)) or Result())

    assert dashboard.main(["--ssh-host", "cluster"]) == 17
    assert calls == [
        (["/usr/local/bin/tmux-opener", "terminal-dashboard", "cluster"], {"check": False})
    ]


class FakeScreen:
    def __init__(self, height: int, width: int, keys: list[int]) -> None:
        self.height = height
        self.width = width
        self.keys = list(keys)
        self.current: dict[int, list[str]] = {}
        self.frames: list[list[str]] = []

    def timeout(self, _milliseconds: int) -> None:
        return None

    def getmaxyx(self) -> tuple[int, int]:
        return self.height, self.width

    def erase(self) -> None:
        self.current = {}

    def addnstr(self, row: int, column: int, text: str, length: int, _attr: int = 0) -> None:
        cells = self.current.setdefault(row, [])
        cells.extend(" " * (column - len(cells)))
        cells[column : column + length] = text[:length]

    def refresh(self) -> None:
        self.frames.append(["".join(self.current[row]) for row in sorted(self.current)])

    def getch(self) -> int:
        return self.keys.pop(0) if self.keys else ord("q")


def _many_downloads(count: int) -> dict[str, object]:
    snapshot = status_response()
    first = snapshot["downloads"][0]
    assert isinstance(first, dict)
    snapshot["downloads"] = [
        {**first, "id": f"download-{index}", "path": f"/scratch/result-{index}.csv"}
        for index in range(1, count + 1)
    ]
    return snapshot


def test_fake_curses_navigation_scrolls_selected_row_and_quits(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = _many_downloads(8)
    monkeypatch.setattr(dashboard, "request_status", lambda *args, **kwargs: snapshot)
    screen = FakeScreen(height=17, width=100, keys=[curses.KEY_DOWN] * 7 + [ord("q")])

    dashboard.run_live_dashboard(
        screen,
        socket_path="/tmp/status.sock",
        cwd="/tmp/work",
        pane="%9",
        ssh_host="cluster",
        timeout=0.75,
    )

    assert screen.frames
    selected = [line for line in screen.frames[-1] if line.startswith(f" {dashboard.GLYPHS['select']}")]
    assert len(selected) == 1 and "result-8.csv" in selected[0]
    assert not any("result-1.csv" in line for line in screen.frames[-1])


def test_fake_curses_bridge_error_recovers_and_q_quits(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = status_response()
    replies: list[object] = [OSError("socket unavailable"), snapshot]

    def request(*_args, **_kwargs):
        reply = replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply

    monkeypatch.setattr(dashboard, "request_status", request)
    screen = FakeScreen(height=12, width=80, keys=[ord("x"), ord("q")])

    dashboard.run_live_dashboard(
        screen,
        socket_path="/tmp/status.sock",
        cwd="/tmp/work",
        pane="%9",
        ssh_host="cluster",
        timeout=0.75,
    )

    assert any(any("ERROR: socket unavailable" in line for line in frame) for frame in screen.frames)
    assert any(any("TRANSFERS" in line for line in frame) for frame in screen.frames[1:])


def test_tmux_dashboard_binding_is_installed_by_a_real_tmux_server() -> None:
    tmux = shutil.which("tmux")
    if tmux is None:
        pytest.skip("tmux is not installed")

    server_name = f"tmux-opener-dashboard-{os.getpid()}"
    subprocess.run([tmux, "-L", server_name, "-f", "/dev/null", "new-session", "-d", "-s", "ci"], check=True)
    try:
        subprocess.run([tmux, "-L", server_name, "run-shell", str(REPO_ROOT / "tmux-opener.tmux")], check=True)
        deadline = time.monotonic() + 3
        prefix_keys = ""
        while time.monotonic() < deadline:
            prefix_keys = subprocess.run(
                [tmux, "-L", server_name, "list-keys", "-T", "prefix"],
                check=True,
                text=True,
                capture_output=True,
            ).stdout
            if "tmux-opener-status" in prefix_keys:
                break
            time.sleep(0.05)
        assert "-T prefix O       display-popup -E" in prefix_keys
        assert "tmux-opener-status" in prefix_keys
        assert "TMUX_OPENER_CWD=#{q:pane_current_path}" in prefix_keys
        assert "TMUX_PANE=#{q:pane_id}" in prefix_keys
    finally:
        subprocess.run([tmux, "-L", server_name, "kill-server"], check=False)


def test_fake_curses_openers_view_cycles_and_saves_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    stored = {"settings": {"rules": [{"pattern": "*.pdf", "opener": "preview"}, {"pattern": "*.pt", "opener": "download"}],
                           "vscode_folder_window": "new", "vscode_file_window": "new", "pdf_viewer": "auto"},
              "path": "/home/alice/.config/tmux-opener/settings.json", "preview_suffixes": [".pdf"]}
    saved: list[dict[str, object]] = []

    def save(settings, *_args) -> None:
        saved.append(settings)
        stored["settings"] = settings

    monkeypatch.setattr(dashboard, "request_status", lambda *args, **kwargs: status_response())
    monkeypatch.setattr(dashboard, "request_settings", lambda *args: json.loads(json.dumps(stored)))
    monkeypatch.setattr(dashboard, "save_settings", save)
    keys = [9, curses.KEY_RIGHT, ord("J"), curses.KEY_UP, ord("x"), ord("q")]
    screen = FakeScreen(height=24, width=100, keys=keys)

    dashboard.run_live_dashboard(screen, socket_path="/tmp/status.sock", cwd="/tmp/work", pane="%9",
                                 ssh_host="cluster", timeout=0.75)

    assert [rule["opener"] for rule in saved[0]["rules"]] == ["download", "download"]
    assert [rule["pattern"] for rule in saved[1]["rules"]] == ["*.pt", "*.pdf"]
    assert saved[2]["rules"] == [{"pattern": "*.pdf", "opener": "download"}]
    assert any("*.pdf" in line and "Download" in line for line in screen.frames[-1])
    assert any("saved" in line for line in screen.frames[-1])
