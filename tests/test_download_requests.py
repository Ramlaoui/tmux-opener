from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from tmux_opener_common import build_download_requests  # noqa: E402


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


def build(
    selection: str,
    cwd: Path,
    ssh_host: str | None = "devbox",
    *,
    ask_destination: bool = False,
) -> list[dict[str, object]] | None:
    return build_download_requests(
        selection,
        str(cwd),
        ssh_host,
        ask_destination=ask_destination,
    )


def expected(path: Path, ssh_host: str | None = "devbox", *, ask_destination: bool = False) -> dict[str, object]:
    request: dict[str, object] = {
        "version": 1,
        "action": "download_file",
        "path": str(path.resolve()),
        "ask_destination": ask_destination,
    }
    if ssh_host:
        request["ssh_host"] = ssh_host
    return request


def test_single_file_request_uses_absolute_path_and_optional_fields(tmp_path: Path) -> None:
    source = touch(tmp_path / "results" / "energy.csv")

    assert build("results/energy.csv", tmp_path) == [expected(source)]
    assert build("results/energy.csv", tmp_path, None, ask_destination=True) == [
        expected(source, None, ask_destination=True)
    ]


def test_newline_separated_files_preserve_order_and_deduplicate(tmp_path: Path) -> None:
    first = touch(tmp_path / "first.txt")
    second = touch(tmp_path / "second.txt")

    assert build("first.txt\nsecond.txt\nfirst.txt", tmp_path) == [
        expected(first),
        expected(second),
    ]


def test_newline_exact_match_precedes_whitespace_splitting_for_spaced_path(tmp_path: Path) -> None:
    spaced = touch(tmp_path / "folder" / "report final.txt")
    other = touch(tmp_path / "other.txt")

    assert build("folder/report final.txt\nother.txt", tmp_path) == [
        expected(spaced),
        expected(other),
    ]


def test_single_quoted_path_with_spaces_is_one_request(tmp_path: Path) -> None:
    source = touch(tmp_path / "folder" / "report final.txt")

    assert build("'folder/report final.txt'", tmp_path) == [expected(source)]


def test_whitespace_separated_existing_paths_use_shlex_and_preserve_order(tmp_path: Path) -> None:
    first = touch(tmp_path / "first.txt")
    second = touch(tmp_path / "second.txt")

    assert build("second.txt first.txt second.txt", tmp_path) == [
        expected(second),
        expected(first),
    ]


def test_line_and_column_suffixes_are_removed_from_each_file(tmp_path: Path) -> None:
    first = touch(tmp_path / "src" / "first.py")
    second = touch(tmp_path / "src" / "second.py")

    assert build("src/first.py:12:4\nsrc/second.py:9", tmp_path) == [
        expected(first),
        expected(second),
    ]


@pytest.mark.parametrize(
    "selection",
    [
        "https://example.test/archive.zip",
        "downloads",
        "missing.txt",
    ],
)
def test_non_regular_or_missing_sources_are_rejected(tmp_path: Path, selection: str) -> None:
    (tmp_path / "downloads").mkdir()

    assert build(selection, tmp_path) is None


def test_invalid_item_rejects_the_entire_multiline_selection(tmp_path: Path) -> None:
    source = touch(tmp_path / "valid.txt")

    assert build(f"valid.txt\n{source.parent / 'missing.txt'}", tmp_path) is None


def test_unmatched_quote_in_one_line_rejects_the_entire_selection(tmp_path: Path) -> None:
    source = touch(tmp_path / "valid.txt")

    assert build(f"valid.txt\n'{source}", tmp_path) is None
