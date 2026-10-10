from __future__ import annotations

import json
import runpy
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("flag", ["--download", "--save-as"])
def test_selection_reaches_client_as_download_requests(tmp_path: Path, flag: str) -> None:
    source = tmp_path / "file with spaces.txt"
    source.write_text("contents")
    socket_path = tmp_path / "client.sock"
    requests = []
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(socket_path))
        server.listen()
        server.settimeout(3)

        def receive() -> None:
            for _ in range(2):
                connection, _ = server.accept()
                with connection:
                    requests.append(json.loads(connection.recv(65536)))
                    connection.sendall(b'{"version":1,"ok":true,"client":"tmux-opener-client"}\n')

        receiver = threading.Thread(target=receive)
        receiver.start()
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/tmux-opener-dispatch"), flag,
             "--socket", str(socket_path), "--cwd", str(tmp_path), "--ssh-host", "devbox",
             "--no-log", "--route-feedback", "never"],
            input=source.name, text=True, capture_output=True, timeout=3,
        )
        receiver.join(timeout=3)
    assert result.returncode == 0, result.stderr
    assert requests == [
        {"version": 1, "action": "ping"},
        {"version": 1, "action": "download_file", "path": str(source),
         "ssh_host": "devbox", "ask_destination": flag == "--save-as"},
    ]


def test_download_without_bridge_does_not_use_opener_fallback(tmp_path: Path) -> None:
    source = tmp_path / "result.txt"
    source.touch()
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/tmux-opener-dispatch"), str(source),
         "--download", "--socket", str(tmp_path / "missing.sock"),
         "--fallback", "command", "--fallback-command", "exit 42", "--no-log"],
        text=True, capture_output=True, timeout=3, env={"PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 1
    assert "downloads require the local client bridge" in result.stderr


@pytest.mark.parametrize("returncode, output", [(0, "chosen file.txt"), (1, "")])
def test_linux_save_dialog_returns_choice_or_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, returncode: int, output: str,
) -> None:
    client = runpy.run_path(str(ROOT / "bin/tmux-opener-client"))
    chosen = tmp_path / output if output else None
    monkeypatch.setattr(client["platform"], "system", lambda: "Linux")
    monkeypatch.setattr(client["shutil"], "which", lambda name: "/bin/zenity" if name == "zenity" else None)
    calls = []

    def dialog(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, returncode, f"{chosen}\n" if chosen else "", "")

    monkeypatch.setattr(client["subprocess"], "run", dialog)
    default = tmp_path / "Downloads" / "report.txt"
    assert client["choose_download_path"](default) == chosen
    assert calls[0] == ["zenity", "--file-selection", "--save", "--title=Save remote file", f"--filename={default}"]
