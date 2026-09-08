from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENT_PATH = REPO_ROOT / "bin" / "tmux-opener-client"


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
