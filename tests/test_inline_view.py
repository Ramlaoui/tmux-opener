from __future__ import annotations

import json
import runpy
import shlex
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import tmux_opener_common as common  # noqa: E402


VIEW = runpy.run_path(str(ROOT / "scripts/tmux-opener-view"))


def which_only(*names: str):
    return lambda name: f"/usr/bin/{name}" if name in names else None


def test_text_uses_bat_at_the_selected_line_or_plain_less(tmp_path: Path) -> None:
    source = tmp_path / "train.py"
    source.write_text("print('hi')\n")

    producer, pager = VIEW["plan"](source, 12, which_only("bat"))
    assert producer == ["/usr/bin/bat", "--color=always", "--paging=never", "--style=numbers",
                        "--highlight-line", "12", "--", str(source)]
    assert pager[0] == "less" and "+12g" in pager and "-+F" in pager

    producer, pager = VIEW["plan"](source, 12, which_only())
    assert producer is None
    assert pager[-2:] == ["--", str(source)] and "-N" in pager and "+12g" in pager


def test_tables_json_binary_and_images_pick_matching_viewers(tmp_path: Path) -> None:
    table = tmp_path / "scores.csv"
    table.write_text('name,score\nalice,"0.9, final"\n')
    text, pager = VIEW["plan"](table, None, which_only("bat"))
    assert "alice  0.9, final" in text and "-S" in pager

    data = tmp_path / "cfg.json"
    data.write_text('{"a": 1}')
    assert VIEW["plan"](data, None, which_only("jq"))[0] == ["jq", "-C", ".", str(data)]
    assert VIEW["plan"](data, None, which_only())[0][1:] == ["-m", "json.tool", str(data)]

    binary = tmp_path / "model.pt"
    binary.write_bytes(b"\0\1\2")
    assert "Binary file" in VIEW["plan"](binary, None, which_only("bat"))[0]

    image = tmp_path / "loss.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n\0")
    assert VIEW["plan"](image, None, which_only("chafa"), (100, 30))[0][:3] == ["chafa", "--format=symbols", "--size=100x28"]
    assert "Install chafa" in VIEW["plan"](image, None, which_only())[0]

    assert VIEW["plan"](tmp_path, None, which_only())[0] == ["ls", "-la", str(tmp_path)]


def test_popup_runs_the_viewer_with_a_quoted_path(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(common.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(common.subprocess, "run", lambda command, **_kwargs: calls.append(command) or subprocess.CompletedProcess(command, 0))

    path = "/work/it's $(here).log"
    assert common.show_inline(path, 7, "/work") == 0

    (popup,) = calls
    assert popup[:8] == ["tmux", "display-popup", "-E", "-w", "90%", "-h", "90%", "-d"]
    assert shlex.split(popup[-1]) == [str(ROOT / "scripts/tmux-opener-view"), path, "--line", "7", "||", "true"]


def test_dispatch_shows_inline_when_the_client_answers_tmux(tmp_path: Path) -> None:
    source = tmp_path / "train.log"
    source.write_text("step 1\n")
    socket_path = tmp_path / "client.sock"
    requests = []
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(socket_path))
        server.listen()
        server.settimeout(3)

        def receive() -> None:
            for reply in (b'{"version":1,"ok":true,"client":"tmux-opener-client"}\n', b'{"ok":true,"opener":"tmux"}\n'):
                connection, _ = server.accept()
                with connection:
                    requests.append(json.loads(connection.recv(65536)))
                    connection.sendall(reply)

        receiver = threading.Thread(target=receive)
        receiver.start()
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        (fake_bin / "tmux").write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {shlex.quote(str(tmp_path / 'tmux.args'))}\n")
        (fake_bin / "tmux").chmod(0o755)
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/tmux-opener-dispatch"), f"{source.name}:3",
             "--socket", str(socket_path), "--cwd", str(tmp_path), "--ssh-host", "devbox", "--no-log"],
            text=True, capture_output=True, timeout=3, stdin=subprocess.DEVNULL,
            env={"PATH": f"{fake_bin}:/usr/bin:/bin", "TMUX": "/tmp/tmux-test,1,0"},
        )
        receiver.join(timeout=3)

    assert result.returncode == 0, result.stderr
    assert requests[1]["inline"] is True and requests[1]["line"] == 3
    tmux_args = (tmp_path / "tmux.args").read_text().splitlines()
    assert tmux_args[0] == "display-popup"
    assert shlex.split(tmux_args[-1])[1:4] == [str(source), "--line", "3"]


def test_view_key_needs_no_bridge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# notes\n")
    shown: list[tuple[object, ...]] = []
    dispatch = runpy.run_path(str(ROOT / "scripts/tmux-opener-dispatch"))
    monkeypatch.setitem(dispatch["main"].__globals__, "show_inline", lambda *args: shown.append(args) or 0)
    monkeypatch.setattr(sys, "argv", ["tmux-opener-dispatch", "notes.md", "--view", "--cwd", str(tmp_path),
                                      "--socket", str(tmp_path / "missing.sock"), "--no-log"])
    assert dispatch["main"]() == 0
    assert shown == [(str(source), None, str(tmp_path))]
