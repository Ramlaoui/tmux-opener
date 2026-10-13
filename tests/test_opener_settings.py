from __future__ import annotations

import json
import runpy
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import tmux_opener_settings as settings_module  # noqa: E402


def test_viewer_detection_uses_desktop_installations(monkeypatch):
    monkeypatch.setattr(settings_module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(settings_module.shutil, "which", lambda _name: None)
    installed = {"/Applications/sioyek.app", "/Applications/Adobe Acrobat DC/Adobe Acrobat.app"}
    monkeypatch.setattr(Path, "is_dir", lambda path: str(path) in installed)
    monkeypatch.setattr(settings_module.os, "access", lambda path, _mode: str(path).endswith("MacOS/sioyek"))
    assert settings_module.available_pdf_viewers() == ["auto", "sioyek", "acrobat", "system"]
    assert settings_module.pdf_application("acrobat") == Path("/Applications/Adobe Acrobat DC/Adobe Acrobat.app")


def test_uninstalled_viewers_are_not_offered(monkeypatch):
    monkeypatch.setattr(settings_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(settings_module.shutil, "which", lambda _name: None)
    assert settings_module.available_pdf_viewers() == ["auto", "system"]


@pytest.mark.parametrize("raw, message", [
    ({"command": "rm -rf ~"}, "unknown setting"),
    ({"rules": [{"pattern": "*.pdf", "opener": "sh -c evil"}]}, "rule opener"),
    ({"rules": [{"pattern": "*.pdf", "opener": "preview", "command": "x"}]}, "exactly a pattern"),
    ({"rules": [{"pattern": "a\nb", "opener": "preview"}]}, "single-line"),
    ({"pdf_viewer": "/usr/bin/evince"}, "pdf_viewer"),
    ({"download_notifications": "always"}, "download_notifications"),
])
def test_settings_accept_only_known_enums(raw: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        settings_module.validate(raw)


def test_first_matching_rule_wins_on_basename_or_full_path() -> None:
    settings = settings_module.validate({"rules": [
        {"pattern": "*/figures/*.png", "opener": "preview"},
        {"pattern": " *.PNG ", "opener": "download"},
        {"pattern": "*.pdf", "opener": "preview"},
    ]})
    assert settings_module.opener_for(settings, "/work/figures/loss.png") == "preview"
    assert settings_module.opener_for(settings, "/work/plots/loss.png") == "download"
    assert settings_module.opener_for(settings, "/work/paper/MAIN.PDF") == "preview"
    assert settings_module.opener_for(settings, "/work/train.py") == "vscode"


def test_broken_settings_file_falls_back_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{not json")
    settings, error = settings_module.load(path)
    assert settings == settings_module.DEFAULTS and error and str(path) in error

    saved = settings_module.save({"pdf_viewer": "system"}, path)
    assert settings_module.load(path) == (saved, None)
    assert json.loads(path.read_text())["pdf_viewer"] == "system"


class RecordingQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[object, ...]] = []

    def submit(self, *job: object) -> dict[str, object]:
        self.jobs.append(job)
        return {"id": f"job-{len(self.jobs)}"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return runpy.run_path(str(ROOT / "bin/tmux-opener-client"))


def client_args(**overrides: object) -> Namespace:
    values: dict[str, object] = {
        "allow_any_ssh_host": False, "allow_ssh_host": ["devbox"], "default_ssh_host": "devbox",
        "dry_run": False, "verbose": False, "ssh_config": None, "pdf_viewer": None,
        "vscode_file_window": None, "vscode_folder_window": None, "download_queue": RecordingQueue(),
    }
    values.update(overrides)
    return Namespace(**values)


def open_request(path: str, target_type: str = "file") -> dict[str, object]:
    return {"version": 1, "action": "open_vscode_remote", "ssh_host": "devbox", "path": path,
            "target_type": target_type, "workspace_path": "/work"}


def test_rules_route_remote_files_to_preview_or_download(client: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    args = client_args()
    assert client["dispatch"]({"version": 1, "action": "set_settings", "settings": {"rules": [
        {"pattern": "*.pdf", "opener": "preview"},
        {"pattern": "*.pt", "opener": "download"},
        {"pattern": "*.html", "opener": "preview"},
    ], "vscode_file_window": "reuse"}}, args)["settings"]["vscode_file_window"] == "reuse"
    monkeypatch.setattr(client["shutil"], "which", lambda name: f"/usr/bin/{name}")
    opened: list[dict[str, object]] = []
    monkeypatch.setitem(client["dispatch"].__globals__, "open_vscode_remote",
                        lambda request, _hosts, _dry, _verbose, **policy: opened.append(policy))

    assert client["dispatch"](open_request("/work/paper.pdf"), args) == {"download_id": "job-1", "state": "queued"}
    client["dispatch"](open_request("/work/model.pt"), args)
    with pytest.raises(client["RequestError"], match="not allowed for .html"):
        client["dispatch"](open_request("/work/report.html"), args)
    client["dispatch"](open_request("/work/train.py"), args)
    client["dispatch"](open_request("/work/figures.pdf", "folder"), args)

    assert args.download_queue.jobs == [
        ("devbox", "/work/paper.pdf", False, None, True),
        ("devbox", "/work/model.pt", False, None, False),
    ]
    # Unmatched files and folders keep the VS Code path, with the settings window policy.
    assert opened == [{"folder_window": "new", "file_window": "reuse"}] * 2
    flagged = client_args(vscode_file_window="new")
    client["dispatch"](open_request("/work/train.py"), flagged)
    assert opened[-1]["file_window"] == "new"


def test_preview_download_refreshes_a_private_cache_copy(client: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_ssh = tmp_path / "ssh"
    # Answer the resume script with a "size mtime" identity line, then the bytes.
    fake_ssh.write_text("#!/bin/sh\nprintf '%s 0\\n%s' \"${#PAYLOAD}\" \"$PAYLOAD\"\n")
    fake_ssh.chmod(0o755)
    notified: list[str] = []
    monkeypatch.setitem(client["download_file"].__globals__, "download_notification", notified.append)

    monkeypatch.setenv("PAYLOAD", "first")
    first = client["download_file"]("devbox", "/work/plot.png", False, str(fake_ssh), preview=True)
    monkeypatch.setenv("PAYLOAD", "second")
    second = client["download_file"]("devbox", "/work/plot.png", False, str(fake_ssh), preview=True)

    destination = Path(str(second["destination"]))
    assert first["destination"] == second["destination"]
    assert destination.read_text() == "second"
    assert destination.parent.parent == tmp_path / "cache" / "tmux-opener" / "preview"
    assert destination.parent.stat().st_mode & 0o777 == 0o700
    assert notified == []


def test_inline_rule_answers_only_senders_that_can_show_popups(client: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    args = client_args()
    client["dispatch"]({"version": 1, "action": "set_settings", "settings": {"rules": [{"pattern": "*.log", "opener": "tmux"}]}}, args)
    opened: list[str] = []
    monkeypatch.setitem(client["dispatch"].__globals__, "open_vscode_remote",
                        lambda request, *_args, **_policy: opened.append(request["path"]))

    assert client["dispatch"]({**open_request("/work/train.log"), "inline": True}, args) == {"opener": "tmux"}
    assert opened == []
    # Older senders, VimTeX and folders cannot show a popup and keep VS Code.
    assert client["dispatch"](open_request("/work/train.log"), args) is None
    client["dispatch"]({**open_request("/work/logs.log", "folder"), "inline": True}, args)
    assert opened == ["/work/train.log", "/work/logs.log"]
    assert args.download_queue.jobs == []


@pytest.mark.parametrize("system, policy, message, expected", [
    ("Darwin", "all", "Downloaded box:/w/a.csv to /d/a.csv", "osascript"),
    ("Linux", "all", "Downloaded box:/w/a.csv to /d/a.csv", "notify-send"),
    ("Darwin", "failures", "Downloaded box:/w/a.csv to /d/a.csv", None),
    ("Linux", "failures", "Download failed for box:/w/a.csv: gone", "notify-send"),
    ("Darwin", "off", "Download failed for box:/w/a.csv: gone", None),
])
def test_download_notifications_follow_the_setting(client: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                   system: str, policy: str, message: str, expected: str | None) -> None:
    settings_module.save({"download_notifications": policy}, tmp_path / "config" / "tmux-opener" / "settings.json")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    notify = client["download_notification"]
    monkeypatch.setattr(notify.__globals__["platform"], "system", lambda: system)
    monkeypatch.setattr(notify.__globals__["shutil"], "which", lambda name: f"/usr/bin/{name}")
    commands: list[list[str]] = []
    monkeypatch.setattr(notify.__globals__["subprocess"], "run", lambda command, **_kwargs: commands.append(command))
    notify(message)
    assert [command[0] for command in commands] == ([expected] if expected else [])
    if commands:
        # The message is an argument, never part of a script or option.
        assert commands[0][-2:] == ["tmux-opener", message]
