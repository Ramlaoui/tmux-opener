#!/usr/bin/env python3
"""Drive the demo tmux session for the documentation recordings.

Runs inside the demo container as `demo`, while a desktop terminal is attached
to the `lab` session through `tmux-opener ssh devbox`:

    docker exec -u demo -e USER=demo tmux-opener-demo python3 scenes.py SCENE

Keys go through tmux itself, so copy-mode and prefix bindings behave exactly as
they do when typed.
"""

from __future__ import annotations

import random
import subprocess
import sys
import time

SESSION = "lab"


def tmux(*args: str) -> str:
    return subprocess.run(["tmux", *args], check=True, capture_output=True, text=True).stdout


def pause(seconds: float) -> None:
    time.sleep(seconds)


def client() -> str:
    return tmux("list-clients", "-t", SESSION, "-F", "#{client_name}").split()[0]


def type_text(text: str) -> None:
    for character in text:
        tmux("send-keys", "-t", SESSION, "-l", character)
        pause(random.uniform(0.035, 0.085))


def run(command: str, settle: float = 1.0) -> None:
    type_text(command)
    pause(0.35)
    tmux("send-keys", "-t", SESSION, "Enter")
    pause(settle)


def reset() -> None:
    """Return to a clean prompt in the project, without any visible typing."""
    tmux("send-keys", "-t", SESSION, "-X", "cancel") if in_mode() else None
    tmux("select-window", "-t", f"{SESSION}:1")
    tmux("send-keys", "-t", SESSION, "C-c")
    tmux("send-keys", "-t", SESSION, "cd ~/vision-lab && clear", "Enter")
    pause(0.4)
    tmux("clear-history", "-t", SESSION)


def in_mode() -> bool:
    return tmux("display-message", "-p", "-t", SESSION, "#{pane_in_mode}").strip() == "1"


def press(*keys: str, gap: float = 0.25) -> None:
    """Send keys to the client as if typed, so prefix bindings and popups see them."""
    name = client()
    for key in keys:
        tmux("send-keys", "-K", "-c", name, key)
        pause(gap)


def copy_key(key: str) -> None:
    """Press a key in copy mode; tmux dispatches it through the copy-mode table."""
    tmux("send-keys", "-t", SESSION, key)


def x(command: str, count: int = 1) -> None:
    tmux("send-keys", "-t", SESSION, "-N", str(count), "-X", command)


def find(text: str, last: bool = True) -> tuple[int, int]:
    rows = tmux("capture-pane", "-p", "-t", SESSION).splitlines()
    hits = [(row, line.index(text)) for row, line in enumerate(rows) if text in line]
    if not hits:
        raise SystemExit(f"not on screen: {text!r}")
    return hits[-1] if last else hits[0]


def select(text: str, length: int | None = None, lines: int = 1) -> None:
    """Enter copy mode and select `text` (or whole lines) the way a person would."""
    row, column = find(text)
    tmux("copy-mode", "-t", SESSION)
    x("top-line")
    x("start-of-line")
    for _ in range(row):
        x("cursor-down")
        pause(0.03)
    pause(0.15)
    if lines > 1 or length == 0:
        x("select-line")
        for _ in range(lines - 1):
            pause(0.18)
            x("cursor-down")
    else:
        x("cursor-right", column) if column else None
        pause(0.2)
        x("begin-selection")
        for _ in range((length or len(text)) - 1):
            x("cursor-right")
            pause(0.012)
    pause(0.7)


def train() -> None:
    run("python train.py", settle=2.2)


# Scenes --------------------------------------------------------------------


def open_url() -> None:
    reset()
    train()
    select("https://github.com/Ramlaoui/tmux-opener")
    copy_key("o")
    pause(6)


def open_vscode() -> None:
    reset()
    train()
    select('File "/home/demo/vision-lab/src/vision/model.py", line 24', lines=1, length=0)
    copy_key("o")
    pause(12)


def localhost() -> None:
    reset()
    train()
    select("http://localhost:8888/?token=7f3a9c")
    copy_key("o")
    pause(7)


def hero() -> None:
    reset()
    train()
    select("https://github.com/Ramlaoui/tmux-opener")
    copy_key("o")
    pause(5)
    select('File "/home/demo/vision-lab/src/vision/model.py", line 24', lines=1, length=0)
    copy_key("o")
    pause(11)


def picker() -> None:
    reset()
    train()
    pause(0.6)
    press("C-b", "o", gap=0.5)
    pause(1.4)
    for character in "8888":
        press(character, gap=0.22)
    pause(1.0)
    press("Enter")
    pause(6)


def inline_view() -> None:
    reset()
    run("find figures paper runs -maxdepth 1 | sort", settle=1.2)
    select("figures/samples.png")
    copy_key("i")
    pause(4.5)
    press("q")
    pause(1.0)
    select("paper/report.pdf")
    copy_key("i")
    pause(3.5)
    press("Space")
    pause(3.0)
    press("q")
    pause(1.0)
    select("runs/exp-42")
    copy_key("i")
    pause(2.0)
    for _ in range(4):
        press("j", gap=0.6)
    pause(1.5)
    press("q")
    pause(0.8)


def download() -> None:
    reset()
    run("cat notes.md", settle=1.0)
    select("runs/*/loss_epoch050.png")
    copy_key("d")
    pause(7)


def save_as() -> None:
    reset()
    run("ls -lh checkpoints/*.ckpt", settle=1.0)
    select("checkpoints/vit_s16_epoch030.ckpt")
    copy_key("D")
    pause(10)


def upload() -> None:
    reset()
    run("cd data && ls", settle=1.0)
    press("C-b", "P", gap=0.4)
    pause(10)
    run("ls -l", settle=2.0)


def dashboard() -> None:
    reset()
    pause(0.5)
    press("C-b", "O", gap=0.5)
    pause(3.5)
    press("j", gap=0.8)
    press("j", gap=0.8)
    press("Tab")
    pause(3.0)
    press("Tab")
    pause(3.0)
    press("q")
    pause(0.5)


SCENES = {name.replace("_", "-"): scene for name, scene in list(globals().items())
          if callable(scene) and getattr(scene, "__module__", "") == __name__
          and name in {"reset", "open_url", "open_vscode", "localhost", "hero", "picker", "inline_view",
                       "download", "save_as", "upload", "dashboard"}}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in SCENES:
        raise SystemExit(f"usage: scenes.py {{{','.join(SCENES)}}}")
    SCENES[sys.argv[1]]()
