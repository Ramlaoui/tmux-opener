from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENT_PATH = REPO_ROOT / "bin" / "tmux-opener-client"
FAKE_CODE = "/opt/bin/code"


def load_client(monkeypatch: Any) -> dict[str, Any]:
    client = runpy.run_path(str(CLIENT_PATH))
    monkeypatch.setattr(client["shutil"], "which", lambda name: FAKE_CODE if name == "code" else None)
    return client


def open_vscode_remote(
    client: dict[str, Any],
    request: dict[str, object],
    *,
    folder_window: str = "new",
    file_window: str = "new",
) -> None:
    client["open_vscode_remote"](
        request,
        {"devbox"},
        True,
        False,
        folder_window=folder_window,
        file_window=file_window,
    )


def test_client_help_exposes_vscode_window_policy_flags() -> None:
    result = subprocess.run(
        [sys.executable, str(CLIENT_PATH), "--help"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    assert "--vscode-folder-window {new,reuse}" in result.stdout
    assert "--vscode-file-window {new,reuse}" in result.stdout


def test_vscode_remote_default_window_policies_are_logged(monkeypatch: Any, capsys: Any) -> None:
    client = load_client(monkeypatch)

    open_vscode_remote(
        client,
        {
            "version": 1,
            "action": "open_vscode_remote",
            "ssh_host": "devbox",
            "path": "/work/project",
            "target_type": "folder",
        },
    )
    output = capsys.readouterr().out
    assert f"dry-run code: {FAKE_CODE} --new-window --remote ssh-remote+devbox /work/project" in output

    open_vscode_remote(
        client,
        {
            "version": 1,
            "action": "open_vscode_remote",
            "ssh_host": "devbox",
            "path": "/work/project/app.py",
            "workspace_path": "/work/project",
            "target_type": "file",
            "line": 12,
            "column": 4,
        },
    )
    output = capsys.readouterr().out
    assert (
        f"dry-run code: {FAKE_CODE} --new-window --goto --remote "
        "ssh-remote+devbox /work/project /work/project/app.py:12:4"
    ) in output


def test_vscode_remote_window_policies_are_configurable(monkeypatch: Any, capsys: Any) -> None:
    client = load_client(monkeypatch)

    open_vscode_remote(
        client,
        {
            "version": 1,
            "action": "open_vscode_remote",
            "ssh_host": "devbox",
            "path": "/work/project",
            "target_type": "folder",
        },
        folder_window="reuse",
    )
    output = capsys.readouterr().out
    assert f"dry-run code: {FAKE_CODE} --reuse-window --remote ssh-remote+devbox /work/project" in output

    open_vscode_remote(
        client,
        {
            "version": 1,
            "action": "open_vscode_remote",
            "ssh_host": "devbox",
            "path": "/work/project/app.py",
            "workspace_path": "/work/project",
            "target_type": "file",
            "line": 12,
        },
        file_window="reuse",
    )
    output = capsys.readouterr().out
    assert (
        f"dry-run code: {FAKE_CODE} --reuse-window --goto --remote "
        "ssh-remote+devbox /work/project /work/project/app.py:12"
    ) in output
