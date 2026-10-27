from __future__ import annotations

import base64
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
    view, pager = VIEW["plan"](table, 3, which_only("bat"))
    assert pager is None and view.start == 1
    assert view.lines[0] == "name   score" and view.lines[1].startswith("─────") and view.lines[2] == "alice  0.9, final"

    notes = tmp_path / "README.md"
    notes.write_text("# Notes\n")
    assert VIEW["plan"](notes, None, which_only("glow", "bat"), (100, 30))[0] == ["/usr/bin/glow", "--style=dark", "--width=98", "--", str(notes)]
    rendered, pager = VIEW["plan"](notes, 1, which_only("bat"))
    assert "\x1b[" in rendered and "Notes" in rendered and "# " not in rendered and "+1g" in pager

    data = tmp_path / "cfg.json"
    data.write_text('{"a": 1}')
    assert VIEW["plan"](data, None, which_only("jq"))[0] == ["jq", "-C", ".", str(data)]
    assert VIEW["plan"](data, None, which_only())[0][1:] == ["-m", "json.tool", str(data)]

    binary = tmp_path / "model.pt"
    binary.write_bytes(b"\0\1\2")
    assert "Binary file" in VIEW["plan"](binary, None, which_only("bat"))[0]

    image = tmp_path / "loss.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n\0")
    assert VIEW["plan"](image, None, which_only("chafa"), (100, 30))[0][:4] == ["chafa", "--format=symbols", "--animate=off", "--size=100x28"]
    assert "Install chafa" in VIEW["plan"](image, None, which_only())[0]
    producer, pager = VIEW["plan"](image, None, which_only("chafa"), (100, 30), pixels=True)
    assert producer[:3] == ["chafa", "--format=kitty", "--passthrough=tmux"] and pager is None

    assert VIEW["plan"](tmp_path, None, which_only())[0] == VIEW["Folder"](tmp_path.absolute(), False)


@pytest.mark.parametrize(("usage", "probe"), [("  --probe=BOOL  Probe terminal", True), ("  --polite=BOOL", False)])
def test_chafa_pixels_use_probe_and_exact_size_only_from_chafa_1_16(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, usage: str, probe: bool
) -> None:
    # chafa 1.14, in Debian trixie, rejects --probe=off, and its --exact-size=on frames are huge.
    chafa = tmp_path / "chafa"
    chafa.write_text(f"#!/bin/sh\necho '{usage}'\n")
    chafa.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    argv = VIEW["chafa_pixels"].__wrapped__()
    assert argv[:3] == ["chafa", "--format=kitty", "--passthrough=tmux"]
    assert ("--probe=off" in argv) is probe and ("--exact-size=on" in argv) is probe


def test_popup_runs_the_viewer_with_a_quoted_path(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(common.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(common.subprocess, "run", lambda command, **_kwargs: calls.append(command) or subprocess.CompletedProcess(command, 0))

    path = "-it's $(here).log"
    assert common.show_inline(path, 7, "/work/#(touch x)") == 0

    (popup,) = calls
    # tmux expands formats in the directory but not in the shell command.
    assert popup[:9] == ["tmux", "display-popup", "-E", "-w", "90%", "-h", "90%", "-d", "/work/##(touch x)"]
    assert shlex.split(popup[-1]) == [str(ROOT / "scripts/tmux-opener-view"), "--line", "7", "--", path, "||", "true"]


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
    assert shlex.split(tmux_args[-1])[1:5] == ["--line", "3", "--", str(source)]


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


def test_pdfs_page_in_pixels_or_fall_back_to_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paper = tmp_path / "paper.pdf"
    paper.write_bytes(b"%PDF-1.4\n\0")
    monkeypatch.setitem(VIEW["plan"].__globals__, "pdf_pages", lambda path, which: 3)
    view, pager = VIEW["plan"](paper, 9, which_only("chafa", "pdftoppm", "pdftotext"), pixels=True)
    assert (view.path, view.pages, view.page, pager) == (paper, 3, 3, None)

    producer, pager = VIEW["plan"](paper, None, which_only("chafa", "pdftoppm", "pdftotext"))
    assert producer == ["pdftotext", "-layout", str(paper), "-"] and pager[0] == "less"
    assert "Binary file" in VIEW["plan"](paper, None, which_only())[0]


def test_pixel_images_open_a_window_with_passthrough(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        stdout = "xterm-ghostty ghostty 1.3.1" if command[1] == "display-message" else ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout)

    monkeypatch.setattr(common.subprocess, "run", fake_run)
    monkeypatch.setenv("TMUX", "/tmp/tmux-test,1,0")
    assert common.show_inline(str(tmp_path / "loss.png"), None, str(tmp_path)) == 0
    window = calls[-1]
    assert window[:2] == ["tmux", "new-window"] and window[-5:] == [";", "set", "-pq", "allow-passthrough", "on"]
    assert shlex.split(window[-6])[1:4] == ["--pixels", "--", str(tmp_path / "loss.png")]

    calls.clear()
    assert common.show_inline(str(tmp_path / "paper.pdf"), None, str(tmp_path)) == 0
    assert calls[-1][1] == "new-window" and "--pixels" in calls[-1][-6]

    calls.clear()
    assert common.show_inline(str(tmp_path / "train.log"), None, str(tmp_path)) == 0
    assert [call[1] for call in calls] == ["display-popup"]

    # Folders get a window too, and the browser downloads with the plugin's settings.
    calls.clear()
    monkeypatch.setenv("TMUX_OPENER_SOCKET", "/run/user/7/opener.sock")
    assert common.show_inline(str(tmp_path), None, str(tmp_path)) == 0
    window = calls[-1]
    assert window[1] == "new-window"
    assert shlex.split(window[-6])[:2] == ["env", "TMUX_OPENER_SOCKET=/run/user/7/opener.sock"]
    assert shlex.split(window[-6])[-5:] == ["--pixels", "--", str(tmp_path), "||", "true"]


def test_pixel_view_ignores_kitty_replies_and_sends_wrapped_png_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    keys = ["\x1b_Gi=7;OK\x1b\\", "q"]
    monkeypatch.setitem(VIEW["run"].__globals__, "read_key", lambda: keys.pop(0))
    assert VIEW["run"](["true", "loss.png"], None) == 0
    assert keys == []

    png = bytes(range(256)) * 40
    sequence = VIEW["kitty_png"](png, {b"i": b"7", b"c": b"30", b"r": b"10"})
    commands = [part.replace(b"\x1b\x1b", b"\x1b") for part in sequence.split(b"\x1bPtmux;")[1:]]
    assert commands[0].startswith(b"\x1b_Ga=T,U=1,f=100,i=7,c=30,r=10,m=1;") and b"m=0;" in commands[-1]
    payload = b"".join(command.split(b";", 1)[1].removesuffix(b"\x1b\\\x1b\\") for command in commands)
    assert base64.b64decode(payload) == png


def test_png_files_split_a_stream_of_concatenated_pngs() -> None:
    import io

    def png(payload: bytes) -> bytes:
        chunk = lambda kind, data: len(data).to_bytes(4, "big") + kind + data + b"crc!"  # noqa: E731
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", payload) + chunk(b"IEND", b"")

    first, second = png(b"IEND inside data"), png(b"x" * 300)
    assert list(VIEW["png_files"](io.BytesIO(first + second + second[:20]))) == [first, second]


def test_folder_browser_queues_marked_entries_on_the_bridge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from test_folder_downloads import serve_bridge

    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / "a.log").write_text("a")
    (tmp_path / "notes.txt").write_text("notes")
    socket_path, requests, stop = tmp_path / "client.sock", [], threading.Event()
    thread = serve_bridge(socket_path, ["download_folder"], requests, stop)
    monkeypatch.setenv("TMUX_OPENER_SOCKET", str(socket_path))
    monkeypatch.setenv("TMUX_OPENER_LOG", str(tmp_path / "sender.log"))
    try:
        note = VIEW["download"]([tmp_path / "notes.txt", tmp_path / "runs"], tmp_path, False)
    finally:
        stop.set()
        thread.join(timeout=5)
    assert note == " queued 2 download(s); the desktop client shows progress"
    sent = [(request["action"], request["path"]) for request in requests if request["action"] != "ping"]
    assert sent == [("download_file", str(tmp_path / "notes.txt")), ("download_folder", str(tmp_path / "runs"))]

    monkeypatch.setenv("TMUX_OPENER_SOCKET", str(tmp_path / "missing.sock"))
    assert "downloads require the local client bridge" in VIEW["download"]([tmp_path / "notes.txt"], tmp_path, False)


def test_markdown_renders_styles_without_shifting_lines() -> None:
    import re

    source = ("# Title\n\nSome **bold**, *italic* and `code` with a [link](https://example.org).\n- [x] done\n"
              "1. first\n> quoted\n```python\nx = 1  # not a heading\n```\n| a | bb |\n|---|---|\n| ccc | d |\n---\n")
    rendered = VIEW["render_markdown"](source, 80)
    plain = [re.sub(r"\x1b\[[0-9;]*m", "", line) for line in rendered.splitlines()]
    assert len(plain) == len(source.splitlines())  # path:N lines stay in place
    assert plain[0] == "Title" and plain[2] == "Some bold, italic and code with a link (https://example.org)."
    assert plain[3] == "• [✓] done" and plain[4] == "1. first" and plain[5] == "▌ quoted"
    assert plain[6].startswith("┌─ python ") and plain[7] == "│ x = 1  # not a heading" and len(plain[8]) == len(plain[6])
    assert plain[9:12] == ["a   │ bb", "────┼───", "ccc │ d"] and set(plain[12]) == {"─"}
