from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from tmux_opener_common import build_request  # noqa: E402


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


def build(selection: str, cwd: Path) -> dict[str, object] | None:
    return build_request(selection, str(cwd), "devbox")


def test_url_fragment_is_preserved_when_wrapped(tmp_path: Path) -> None:
    request = build("(https://example.test/docs#install)", tmp_path)

    assert request == {
        "version": 1,
        "action": "open_url",
        "url": "https://example.test/docs#install",
    }


def test_soft_wrapped_url_removes_copy_mode_whitespace(tmp_path: Path) -> None:
    request = build(
        "https://example.test/docs/very-long- \r\n"
        " path?token=abc#install",
        tmp_path,
    )

    assert request == {
        "version": 1,
        "action": "open_url",
        "url": "https://example.test/docs/very-long-path?token=abc#install",
    }


def test_soft_wrapped_url_preserves_encoded_spaces(tmp_path: Path) -> None:
    request = build("https://example.test/docs/a%20b", tmp_path)

    assert request is not None
    assert request["url"] == "https://example.test/docs/a%20b"


def test_bare_localhost_port_builds_remote_localhost_request(tmp_path: Path) -> None:
    request = build("localhost:8080", tmp_path)

    assert request == {
        "version": 1,
        "action": "open_remote_localhost",
        "scheme": "http",
        "remote_host": "localhost",
        "remote_port": 8080,
        "path": "",
        "query": "",
        "fragment": "",
        "ssh_host": "devbox",
    }


def test_localhost_url_preserves_path_query_and_fragment(tmp_path: Path) -> None:
    request = build("(https://127.0.0.1:8888/lab/tree/notebook.ipynb?token=abc#cell)", tmp_path)

    assert request == {
        "version": 1,
        "action": "open_remote_localhost",
        "scheme": "https",
        "remote_host": "127.0.0.1",
        "remote_port": 8888,
        "path": "/lab/tree/notebook.ipynb",
        "query": "token=abc",
        "fragment": "cell",
        "ssh_host": "devbox",
    }


def test_unspecified_bind_address_maps_to_loopback(tmp_path: Path) -> None:
    request = build("http://0.0.0.0:3000/app", tmp_path)

    assert request is not None
    assert request["action"] == "open_remote_localhost"
    assert request["remote_host"] == "127.0.0.1"
    assert request["remote_port"] == 3000


def test_python_traceback_uses_innermost_frame(tmp_path: Path) -> None:
    outer = touch(tmp_path / "app.py")
    inner = touch(tmp_path / "src" / "worker.py")

    request = build(
        f"""Traceback (most recent call last):
  File "{outer}", line 3, in <module>
    run()
  File "{inner}", line 17, in run
    raise RuntimeError("boom")
RuntimeError: boom
""",
        tmp_path,
    )

    assert request is not None
    assert request["path"] == str(inner)
    assert request["target_type"] == "file"
    assert request["line"] == 17


def test_pytest_failure_nodeid_resolves_relative_to_cwd(tmp_path: Path) -> None:
    test_file = touch(tmp_path / "tests" / "test_widget.py")

    request = build("FAILED tests/test_widget.py::test_renders - AssertionError", tmp_path)

    assert request is not None
    assert request["path"] == str(test_file)
    assert request["workspace_path"] == str(tmp_path)
    assert "line" not in request
    assert "column" not in request


def test_compiler_style_line_column_strips_wrapping_punctuation(tmp_path: Path) -> None:
    source = touch(tmp_path / "src" / "main.c")

    request = build("(src/main.c:12:4): error: expected ';'", tmp_path)

    assert request is not None
    assert request["path"] == str(source)
    assert request["line"] == 12
    assert request["column"] == 4


def test_quoted_path_with_spaces_and_line(tmp_path: Path) -> None:
    source = touch(tmp_path / "src" / "quoted file.py")

    request = build('"src/quoted file.py:5"', tmp_path)

    assert request is not None
    assert request["path"] == str(source)
    assert request["line"] == 5


def test_existing_relative_filename_without_slash_can_have_line(tmp_path: Path) -> None:
    source = touch(tmp_path / "Makefile")

    request = build("Makefile:9", tmp_path)

    assert request is not None
    assert request["path"] == str(source)
    assert request["workspace_path"] == str(tmp_path)
    assert request["line"] == 9


def test_folder_target_type_is_preserved(tmp_path: Path) -> None:
    folder = tmp_path / "src"
    folder.mkdir()

    request = build("src", tmp_path)

    assert request is not None
    assert request["path"] == str(folder)
    assert request["target_type"] == "folder"


def test_soft_wrapped_path_joined_after_directory_boundary(tmp_path: Path) -> None:
    target = touch(
        tmp_path
        / "entaloracle/src/config/experiments/finetune/uma/from_ssl"
        / "distill_target_labels_uma_s_1p1_oc20_seed20260527_ec_compref_loaded_model.yaml"
    )

    request = build(
        "entaloracle/src/config/experiments/finetune/uma/from_ssl/\n"
        "distill_target_labels_uma_s_1p1_oc20_seed20260527_ec_compref_loaded_model.yaml",
        tmp_path,
    )

    assert request is not None
    assert request["path"] == str(target)
    assert request["target_type"] == "file"


def test_soft_wrapped_path_joined_inside_filename(tmp_path: Path) -> None:
    target = touch(
        tmp_path
        / "entaloracle/src/config/experiments/finetune/uma/from_ssl"
        / "distill_target_labels_uma_s_1p1_oc20_seed20260527_ec_compref_loaded_model.yaml"
    )

    request = build(
        "entaloracle/src/config/experiments/finetune/uma/from_ssl/distill_target_\n"
        "labels_uma_s_1p1_oc20_seed20260527_ec_compref_loaded_model.yaml",
        tmp_path,
    )

    assert request is not None
    assert request["path"] == str(target)
    assert request["target_type"] == "file"


def test_random_text_is_not_treated_as_a_path(tmp_path: Path) -> None:
    assert build("this failed at line 12 but no file here", tmp_path) is None
    assert build("not_a_real_file.py", tmp_path) is None
