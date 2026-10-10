from __future__ import annotations

import json
import runpy
import shlex
import socket
import threading
import time
from argparse import Namespace
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENT_PATH = REPO_ROOT / "bin" / "tmux-opener-client"


def load_client() -> dict[str, Any]:
    return runpy.run_path(str(CLIENT_PATH))


def write_fake_ssh(path: Path) -> Path:
    path.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path

capture = os.environ.get("TMUX_OPENER_FAKE_SSH_CAPTURE")
if capture:
    Path(capture).write_text(json.dumps(sys.argv[1:]), encoding="utf-8")

gate = os.environ.get("TMUX_OPENER_FAKE_SSH_GATE")
while gate and not Path(gate).exists():
    time.sleep(0.01)

if os.environ.get("TMUX_OPENER_FAKE_SSH_FAIL"):
    sys.stderr.buffer.write(b"remote cat failed\\n")
    raise SystemExit(17)

sys.stdout.buffer.write(bytes.fromhex(os.environ.get("TMUX_OPENER_FAKE_SSH_BYTES", "")))
""",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def configure_fake_ssh(
    monkeypatch: Any,
    tmp_path: Path,
    *,
    payload: bytes = b"",
    fail: bool = False,
    gate: Path | None = None,
) -> tuple[Path, Path]:
    fake_ssh = write_fake_ssh(tmp_path / "fake-ssh")
    capture = tmp_path / "ssh-argv.json"
    monkeypatch.setenv("TMUX_OPENER_FAKE_SSH_CAPTURE", str(capture))
    monkeypatch.setenv("TMUX_OPENER_FAKE_SSH_BYTES", payload.hex())
    monkeypatch.delenv("TMUX_OPENER_FAKE_SSH_FAIL", raising=False)
    monkeypatch.delenv("TMUX_OPENER_FAKE_SSH_GATE", raising=False)
    if fail:
        monkeypatch.setenv("TMUX_OPENER_FAKE_SSH_FAIL", "1")
    if gate is not None:
        monkeypatch.setenv("TMUX_OPENER_FAKE_SSH_GATE", str(gate))
    return fake_ssh, capture


def patch_downloads(client: dict[str, Any], monkeypatch: Any, directory: Path) -> None:
    globals_ = client["download_file"].__globals__
    monkeypatch.setitem(globals_, "downloads_directory", lambda: directory)
    monkeypatch.setitem(globals_, "download_notification", lambda _message: None)


def client_args(**overrides: object) -> Namespace:
    values: dict[str, object] = {
        "allow_any_ssh_host": False,
        "allow_ssh_host": ["devbox"],
        "allow_url_scheme": ["http", "https"],
        "default_ssh_host": None,
        "dry_run": False,
        "once": False,
        "ssh_config": None,
        "verbose": False,
        "vscode_file_window": "new",
        "vscode_folder_window": "new",
    }
    values.update(overrides)
    return Namespace(**values)


def send_socket_request(socket_path: Path, request: dict[str, object]) -> dict[str, object]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(2)
        connection.connect(str(socket_path))
        connection.sendall(json.dumps(request).encode("utf-8") + b"\n")
        return json.loads(connection.recv(65536).decode("utf-8"))


def ssh_option_values(argv: list[str]) -> set[str]:
    values: set[str] = set()
    for index, argument in enumerate(argv):
        if argument == "-o" and index + 1 < len(argv):
            values.add(argv[index + 1])
        elif argument.startswith("-o") and len(argument) > 2:
            values.add(argument[2:])
    return values


def test_download_file_preserves_bytes_and_quotes_remote_metacharacters(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    client = load_client()
    downloads = tmp_path / "Downloads"
    patch_downloads(client, monkeypatch, downloads)
    payload = b"\x00first\nsecond\xff\x00"
    fake_ssh, capture = configure_fake_ssh(monkeypatch, tmp_path, payload=payload)
    remote_path = "/remote dir/it's;[$HOME].bin"

    client["download_file"]("devbox", remote_path, False, str(fake_ssh))

    destination = downloads / Path(remote_path).name
    assert destination.read_bytes() == payload
    argv = json.loads(capture.read_text(encoding="utf-8"))
    assert argv[-2] == "devbox"
    assert argv[-1] == (
        f"test -f {shlex.quote(remote_path)} && cat -- {shlex.quote(remote_path)}"
    )


def test_download_file_isolates_ssh_and_honors_custom_config(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    client = load_client()
    downloads = tmp_path / "Downloads"
    patch_downloads(client, monkeypatch, downloads)
    config = tmp_path / "ssh config"
    config.write_text("Host devbox\n", encoding="utf-8")
    fake_ssh, capture = configure_fake_ssh(monkeypatch, tmp_path, payload=b"isolated")

    client["download_file"](
        "devbox",
        "/remote/isolated.bin",
        False,
        str(fake_ssh),
        ssh_config=str(config),
        verbose=False,
    )

    argv = json.loads(capture.read_text(encoding="utf-8"))
    options = ssh_option_values(argv)
    assert {
        "ControlMaster=no",
        "ClearAllForwardings=yes",
        "PermitLocalCommand=no",
        "ForkAfterAuthentication=no",
    } <= options
    control_index = argv.index("-S")
    assert argv[control_index + 1] == "none"
    config_index = argv.index("-F")
    assert argv[config_index + 1] == str(config)
    assert config_index < argv.index("--")
    assert (downloads / "isolated.bin").read_bytes() == b"isolated"


@pytest.mark.parametrize("fail", [False, True])
def test_default_download_logs_omit_paths_and_ssh_stderr(
    monkeypatch: Any, tmp_path: Path, capsys: Any, fail: bool,
) -> None:
    client = load_client()
    secret = "synthetic-private-download"
    monkeypatch.setitem(client["download_file"].__globals__, "downloads_directory", lambda: tmp_path / secret)
    monkeypatch.setattr(client["shutil"], "which", lambda _name: None)
    fake_ssh, _capture = configure_fake_ssh(monkeypatch, tmp_path, payload=b"bytes", fail=fail)

    client["download_file"]("devbox", f"/remote/{secret}.bin", False, str(fake_ssh))

    output = capsys.readouterr().out
    assert secret not in output
    assert "remote cat failed" not in output
    assert ("download failed" if fail else "download completed") in output


def test_download_file_collision_keeps_existing_files_and_uses_numbered_name(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    client = load_client()
    downloads = tmp_path / "Downloads"
    patch_downloads(client, monkeypatch, downloads)
    destination = downloads / "report.bin"
    first_collision = downloads / "report (1).bin"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"original")
    first_collision.write_bytes(b"also original")
    payload = b"downloaded"
    fake_ssh, _capture = configure_fake_ssh(monkeypatch, tmp_path, payload=payload)

    client["download_file"]("devbox", "/remote/report.bin", False, str(fake_ssh))

    assert destination.read_bytes() == b"original"
    assert first_collision.read_bytes() == b"also original"
    assert (downloads / "report (2).bin").read_bytes() == payload


def test_download_file_ssh_failure_leaves_no_final_or_part_file(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    client = load_client()
    downloads = tmp_path / "Downloads"
    patch_downloads(client, monkeypatch, downloads)
    fake_ssh, _capture = configure_fake_ssh(monkeypatch, tmp_path, fail=True)

    client["download_file"]("devbox", "/remote/failure.bin", False, str(fake_ssh))

    assert list(downloads.iterdir()) == []


def test_choose_download_path_cancellation_does_not_start_ssh(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    client = load_client()
    downloads = tmp_path / "Downloads"
    patch_downloads(client, monkeypatch, downloads)
    fake_ssh, capture = configure_fake_ssh(monkeypatch, tmp_path, payload=b"should not run")
    monkeypatch.setitem(
        client["download_file"].__globals__,
        "choose_download_path",
        lambda _default: None,
    )

    client["download_file"]("devbox", "/remote/cancelled.bin", True, str(fake_ssh))

    assert not capture.exists()
    assert list(downloads.iterdir()) == []


def test_chosen_download_path_writes_bytes_and_rejects_existing_destination(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    client = load_client()
    downloads = tmp_path / "Downloads"
    patch_downloads(client, monkeypatch, downloads)
    chosen = tmp_path / "picked" / "saved as.bin"
    chosen.parent.mkdir()
    fake_ssh, capture = configure_fake_ssh(monkeypatch, tmp_path, payload=b"picked bytes")
    monkeypatch.setitem(
        client["download_file"].__globals__,
        "choose_download_path",
        lambda _default: chosen,
    )

    client["download_file"]("devbox", "/remote/result.bin", True, str(fake_ssh))

    assert chosen.read_bytes() == b"picked bytes"
    capture.unlink()
    chosen.write_bytes(b"keep this")
    client["download_file"]("devbox", "/remote/result.bin", True, str(fake_ssh))

    assert chosen.read_bytes() == b"keep this"
    assert not capture.exists()


@pytest.mark.parametrize(
    ("request_data", "message"),
    [
        (
            {"version": 1, "action": "download_file", "ssh_host": "other", "path": "/tmp/a"},
            "ssh_host is not allowed",
        ),
        (
            {
                "version": 1,
                "action": "download_file",
                "ssh_host": "devbox",
                "path": "/tmp/a",
                "ask_destination": "yes",
            },
            "ask_destination must be a boolean",
        ),
        (
            {"version": 1, "action": "download_file", "ssh_host": "devbox", "path": "relative"},
            "path must be an absolute remote path",
        ),
        (
            {
                "version": 1,
                "action": "download_file",
                "ssh_host": "devbox",
                "path": "/tmp/a\nb",
            },
            "download path must name a file and contain no newlines",
        ),
    ],
)
def test_dispatch_rejects_invalid_downloads_before_starting_workers(
    monkeypatch: Any,
    request_data: dict[str, object],
    message: str,
) -> None:
    client = load_client()
    started: list[object] = []

    def fake_thread(*args: object, **kwargs: object) -> None:
        started.append((args, kwargs))

    monkeypatch.setattr(client["threading"], "Thread", fake_thread)

    with pytest.raises(client["RequestError"], match=message):
        client["dispatch"](request_data, client_args())

    assert started == []


def test_download_dispatch_is_async_while_ping_remains_responsive(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    client = load_client()
    downloads = tmp_path / "Downloads"
    patch_downloads(client, monkeypatch, downloads)
    gate = tmp_path / "release-download"
    payload = b"eventually downloaded"
    fake_ssh, _capture = configure_fake_ssh(monkeypatch, tmp_path, payload=payload, gate=gate)
    monkeypatch.setattr(
        client["shutil"],
        "which",
        lambda name: str(fake_ssh) if name == "ssh" else None,
    )

    socket_path = tmp_path / "opener.sock"
    server = client["bind_server"](str(socket_path))
    args = client_args()
    stop = threading.Event()

    def run_server() -> None:
        try:
            client["serve"](server, args, stop)
        finally:
            server.cleanup()

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    request = {
        "version": 1,
        "action": "download_file",
        "ssh_host": "devbox",
        "path": "/remote/async.bin",
    }

    try:
        assert send_socket_request(socket_path, request) == {"ok": True}
        assert send_socket_request(socket_path, {"version": 1, "action": "ping"})["ok"] is True
        assert not (downloads / "async.bin").exists()

        gate.touch()
        destination = downloads / "async.bin"
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not destination.exists():
            time.sleep(0.01)
        assert destination.read_bytes() == payload
    finally:
        stop.set()

    server_thread.join(timeout=2)
    assert not server_thread.is_alive()
