from __future__ import annotations

import json
import os
import py_compile
import shutil
import socket
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_command(command: list[str | Path], *, cwd: Path = REPO_ROOT, **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(part) for part in command],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        **kwargs,
    )


def compile_script(relative_path: str) -> None:
    py_compile.compile(str(REPO_ROOT / relative_path), doraise=True)


def package_archive(script_name: str, tag: str, archive_name: str, dist_dir: Path) -> Path:
    archive = dist_dir / archive_name
    checksum = archive.with_name(f"{archive.name}.sha256")
    archive.unlink(missing_ok=True)
    checksum.unlink(missing_ok=True)

    env = {**os.environ, "TMUX_OPENER_DIST_DIR": str(dist_dir)}
    result = run_command([REPO_ROOT / "scripts" / script_name, tag], env=env)

    assert result.stdout.strip() == str(archive)
    assert archive.is_file()
    assert checksum.is_file()
    return archive


def archive_names(archive: Path) -> set[str]:
    with tarfile.open(archive, "r:gz") as handle:
        return set(handle.getnames())


def extract_archive(archive: Path, destination: Path) -> Path:
    with tarfile.open(archive, "r:gz") as handle:
        try:
            handle.extractall(destination, filter="data")
        except TypeError:
            handle.extractall(destination)
    roots = [path for path in destination.iterdir() if path.is_dir()]
    assert len(roots) == 1
    return roots[0]


def assert_client_ping(script_path: Path, socket_path: Path) -> None:
    process = subprocess.Popen(
        [
            sys.executable,
            str(script_path),
            "--socket",
            str(socket_path),
            "--once",
            "--dry-run",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    try:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if socket_path.exists():
                break
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout else ""
                raise AssertionError(f"client exited before creating socket:\n{output}")
            time.sleep(0.05)
        else:
            raise AssertionError("client did not create socket")

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1.0)
            client.connect(str(socket_path))
            client.sendall(b'{"version":1,"action":"ping"}\n')
            response = json.loads(client.recv(65536).decode("utf-8"))

        assert response.get("ok") is True
        assert response.get("client") == "tmux-opener-client"
        process.wait(timeout=3.0)
        assert process.returncode == 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)


def test_python_entrypoints_compile() -> None:
    for relative_path in [
        "bin/tmux-opener",
        "bin/tmux-opener-client",
        "scripts/tmux-opener-dispatch",
        "scripts/tmux-opener-pick",
        "scripts/tmux-opener-send",
        "scripts/tmux_opener_common.py",
    ]:
        compile_script(relative_path)


def test_client_cli_help() -> None:
    for relative_path in ["bin/tmux-opener", "bin/tmux-opener-client"]:
        result = run_command([sys.executable, REPO_ROOT / relative_path, "--help"])
        assert "usage:" in result.stdout


def test_client_ping_protocol(tmp_path: Path) -> None:
    assert_client_ping(REPO_ROOT / "bin" / "tmux-opener-client", tmp_path / "client.sock")


def test_tmux_plugin_key_bindings() -> None:
    tmux = shutil.which("tmux")
    if tmux is None:
        pytest.skip("tmux is not installed")

    server_name = f"tmux-opener-pytest-{os.getpid()}"
    run_command([tmux, "-L", server_name, "-f", "/dev/null", "new-session", "-d", "-s", "ci"])
    try:
        run_command([tmux, "-L", server_name, "run-shell", REPO_ROOT / "tmux-opener.tmux"])
        vi_keys = run_command([tmux, "-L", server_name, "list-keys", "-T", "copy-mode-vi"]).stdout
        emacs_keys = run_command([tmux, "-L", server_name, "list-keys", "-T", "copy-mode"]).stdout
        prefix_keys = run_command([tmux, "-L", server_name, "list-keys", "-T", "prefix"]).stdout
        assert "tmux-opener-dispatch" in vi_keys
        assert "tmux-opener-dispatch" in emacs_keys
        assert "tmux-opener-pick" in prefix_keys
        assert "display-popup" in prefix_keys
        assert "display-popup -E" not in prefix_keys
        assert "--target-pane #{pane_id}" not in prefix_keys
        assert "-d \"#{pane_current_path}\"" in prefix_keys
    finally:
        subprocess.run([tmux, "-L", server_name, "kill-server"], check=False)


def test_server_archive_contents(tmp_path: Path) -> None:
    archive = package_archive(
        "package-server-plugin",
        "vpytest",
        "tmux-opener-server-vpytest.tar.gz",
        tmp_path / "dist",
    )

    assert archive_names(archive) == {
        "tmux-opener",
        "tmux-opener/README.md",
        "tmux-opener/tmux-opener.tmux",
        "tmux-opener/scripts",
        "tmux-opener/scripts/tmux-opener-dispatch",
        "tmux-opener/scripts/tmux-opener-pick",
        "tmux-opener/scripts/tmux-opener-send",
        "tmux-opener/scripts/tmux_opener_common.py",
    }


def test_client_archive_contents(tmp_path: Path) -> None:
    archive = package_archive(
        "package-client",
        "vpytest",
        "tmux-opener-client-vpytest.tar.gz",
        tmp_path / "dist",
    )

    assert archive_names(archive) == {
        "tmux-opener-client",
        "tmux-opener-client/README.md",
        "tmux-opener-client/bin",
        "tmux-opener-client/bin/tmux-opener",
        "tmux-opener-client/bin/tmux-opener-client",
    }


def test_extracted_client_entrypoints_work(tmp_path: Path) -> None:
    archive = package_archive(
        "package-client",
        "vpytest-extracted",
        "tmux-opener-client-vpytest-extracted.tar.gz",
        tmp_path / "dist",
    )
    root = extract_archive(archive, tmp_path / "extract")

    for script_name in ["tmux-opener", "tmux-opener-client"]:
        result = run_command([sys.executable, root / "bin" / script_name, "--help"])
        assert "usage:" in result.stdout

    assert_client_ping(root / "bin" / "tmux-opener-client", tmp_path / "extracted-client.sock")
