from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PICKER = REPO_ROOT / "scripts" / "tmux-opener-pick"


def run_picker(source_text: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, PICKER, "--print-candidates", "--cwd", str(REPO_ROOT), *args],
        input=source_text,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def test_print_candidates_ranks_newer_visible_lines_first_and_dedupes() -> None:
    result = run_picker(
        "\n".join(
            [
                "top https://example.com/docs and scripts/tmux-opener-send:27",
                "middle ./scripts/tmux-opener-dispatch:40",
                "bottom repeats https://example.com/docs.",
            ]
        )
    )

    assert result.stdout.splitlines() == [
        "https://example.com/docs",
        "./scripts/tmux-opener-dispatch:40",
        "scripts/tmux-opener-send:27",
    ]


def test_no_fzf_alias_prints_candidates_without_requiring_fzf() -> None:
    result = subprocess.run(
        [sys.executable, PICKER, "--no-fzf", "--cwd", str(REPO_ROOT)],
        input="open ./scripts/tmux-opener-send:1\n",
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    assert result.stdout.strip() == "./scripts/tmux-opener-send:1"
