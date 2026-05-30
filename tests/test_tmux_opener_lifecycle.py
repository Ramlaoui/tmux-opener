from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TMUX_OPENER = REPO_ROOT / "bin" / "tmux-opener"


def run_tmux_opener(
    args: list[str | Path],
    *,
    home: Path,
    path_prefix: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "HOME": str(home)}
    if path_prefix is not None:
        env["PATH"] = f"{path_prefix}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        [sys.executable, str(TMUX_OPENER), *[str(arg) for arg in args]],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        env=env,
    )


def write_fake_ssh(bin_dir: Path, stdout: str, returncode: int = 0) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import sys",
                "if '-G' not in sys.argv:",
                "    print('expected ssh -G invocation', file=sys.stderr)",
                "    raise SystemExit(64)",
                f"sys.stdout.write({stdout!r})",
                f"raise SystemExit({returncode})",
                "",
            ]
        )
    )
    ssh.chmod(0o755)


def test_doctor_reports_local_diagnostics(tmp_path: Path) -> None:
    home = tmp_path / "home"
    state_dir = tmp_path / "state"
    ssh_config = home / ".ssh" / "config"
    snippet_dir = home / ".ssh" / "tmux-opener.d"
    fake_bin = tmp_path / "bin"
    socket_path = state_dir / "work.sock"

    write_fake_ssh(fake_bin, "user alice\n")
    run_tmux_opener(
        [
            "install-host",
            "work",
            "--state-dir",
            state_dir,
            "--ssh-config",
            ssh_config,
            "--snippet-dir",
            snippet_dir,
        ],
        home=home,
        path_prefix=fake_bin,
    )

    write_fake_ssh(
        fake_bin,
        f"user alice\nremoteforward /tmp/tmux-opener-alice.sock {socket_path}\n",
    )
    result = run_tmux_opener(
        [
            "doctor",
            "work",
            "--state-dir",
            state_dir,
            "--ssh-config",
            ssh_config,
            "--snippet-dir",
            snippet_dir,
        ],
        home=home,
        path_prefix=fake_bin,
    )

    assert f"managed include: ok (Include {snippet_dir}/*.conf)" in result.stdout
    assert f"managed snippet: ok ({snippet_dir / 'work.conf'})" in result.stdout
    assert f"  remoteforward /tmp/tmux-opener-alice.sock {socket_path}" in result.stdout
    assert f"expected local socket: {socket_path}" in result.stdout
    assert "local client ping: failed" in result.stdout
    assert "expected remote socket: /tmp/tmux-opener-alice.sock" in result.stdout
    assert "next: run `tmux-opener restart-client work`" in result.stdout


def test_status_can_infer_host_from_socket_name(tmp_path: Path) -> None:
    home = tmp_path / "home"
    state_dir = tmp_path / "state"
    socket_path = state_dir / "work.sock"
    socket_path.parent.mkdir(parents=True)
    socket_path.touch()

    result = run_tmux_opener(
        ["status", "--state-dir", state_dir, "--snippet-dir", tmp_path / "snippets"],
        home=home,
    )

    assert "host: work" in result.stdout
    assert f"local socket: {socket_path} (exists)" in result.stdout
    assert "client ping: failed" in result.stdout
    assert f"log path: {state_dir / 'work.log'}" in result.stdout
    assert "expected default/allowed SSH host: work" in result.stdout


def test_restart_client_dry_run_uses_host_socket_defaults(tmp_path: Path) -> None:
    home = tmp_path / "home"
    state_dir = tmp_path / "state"

    result = run_tmux_opener(["restart-client", "work", "--state-dir", state_dir, "--dry-run"], home=home)

    assert f"local client already stopped: {state_dir / 'work.sock'}" in result.stdout
    assert "would start local client:" in result.stdout
    assert "--default-ssh-host work --allow-ssh-host work" in result.stdout
    assert f"would log to: {state_dir / 'work.log'}" in result.stdout


def test_install_service_dry_run_prints_user_systemd_unit(tmp_path: Path) -> None:
    home = tmp_path / "home"
    state_dir = tmp_path / "state"

    result = run_tmux_opener(
        ["install-service", "work", "--systemd-user", "--dry-run", "--state-dir", state_dir],
        home=home,
    )

    assert "# suggested path: ~/.config/systemd/user/tmux-opener-work.service" in result.stdout
    assert "[Unit]" in result.stdout
    assert "[Service]" in result.stdout
    assert f"--socket {state_dir / 'work.sock'}" in result.stdout
    assert "--default-ssh-host work --allow-ssh-host work" in result.stdout
