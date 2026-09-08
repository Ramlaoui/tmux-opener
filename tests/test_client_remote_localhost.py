from __future__ import annotations

import runpy
import shutil
import subprocess
from argparse import Namespace
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENT_PATH = REPO_ROOT / "bin" / "tmux-opener-client"


def load_client() -> dict[str, Any]:
    return runpy.run_path(str(CLIENT_PATH))


def args(**overrides: object) -> Namespace:
    values = {
        "dry_run": True,
        "verbose": False,
        "ssh_config": None,
        "localhost_forward_start_port": 18000,
        "localhost_forward_end_port": 18999,
    }
    values.update(overrides)
    return Namespace(**values)


def request(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "version": 1,
        "action": "open_remote_localhost",
        "ssh_host": "devbox",
        "scheme": "http",
        "remote_host": "localhost",
        "remote_port": 8080,
        "path": "/docs",
        "query": "token=abc",
        "fragment": "install",
    }
    values.update(overrides)
    return values


def effective_config(command: list[str]) -> dict[str, list[str]]:
    result = subprocess.run(
        [command[0], "-G", *command[1:]], capture_output=True, text=True, check=True
    )
    options: dict[str, list[str]] = {}
    for line in result.stdout.splitlines():
        key, value = line.split(" ", 1)
        options.setdefault(key, []).append(value)
    return options


@pytest.mark.parametrize("proxy", ["ProxyJump jump-example", "ProxyCommand nc %h %p"])
def test_auxiliary_forward_preserves_config_without_inheriting_forwards(tmp_path: Path, proxy: str) -> None:
    ssh = shutil.which("ssh")
    if ssh is None:
        pytest.skip("OpenSSH is required")
    client = load_client()
    included = tmp_path / "included config"
    included.write_text(
        'Host devbox\n'
        '    HostName 192.0.2.10\n'
        '    User service\n'
        '    Port 2222\n'
        f'    IdentityFile "{tmp_path}/identity one"\n'
        f'    IdentityFile "{tmp_path}/identity two"\n'
        f'    CertificateFile "{tmp_path}/certificate file"\n'
        f'    UserKnownHostsFile "{tmp_path}/known hosts" "{tmp_path}/other hosts"\n'
        '    StrictHostKeyChecking yes\n'
        '    IdentitiesOnly yes\n'
        f'    {proxy}\n'
        f'    RemoteForward {tmp_path}/bridge {tmp_path}/client\n'
        '    LocalForward 127.0.0.1:19001 localhost:19001\n'
        '    ClearAllForwardings no\n'
        '    ControlMaster auto\n'
        f'    ControlPath {tmp_path}/existing-master\n'
        'Match originalhost devbox\n'
        f'    IdentityFile "{tmp_path}/matched identity"\n'
    )
    config = tmp_path / "custom config"
    config.write_text(f'Include "{included}"\n')
    original = effective_config([ssh, "-F", str(config), "--", "devbox"])
    master, forward = client["localhost_forward_commands"](
        "devbox", "localhost", 8080, 18080, str(tmp_path / "private-master"), str(config)
    )
    isolated = effective_config(master)
    explicit = effective_config(forward)

    assert "remoteforward" in original
    assert "localforward" in original
    assert "remoteforward" not in isolated
    assert "localforward" not in isolated
    assert "remoteforward" not in explicit
    assert explicit["localforward"] == ["[127.0.0.1]:18080 [localhost]:8080"]
    for option in (
        "hostname", "user", "port", "identityfile", "certificatefile",
        "userknownhostsfile", "stricthostkeychecking", "identitiesonly",
        "proxyjump", "proxycommand",
    ):
        assert isolated.get(option) == original.get(option)


def test_forward_control_cannot_fall_back_to_connection(tmp_path: Path) -> None:
    if shutil.which("ssh") is None:
        pytest.skip("OpenSSH is required")
    client = load_client()
    _, forward = client["localhost_forward_commands"](
        "invalid.example", "localhost", 8080, 18080, str(tmp_path / "missing"), None
    )
    result = subprocess.run(forward, capture_output=True, timeout=2, check=False)
    assert result.returncode != 0
    assert b"Control socket connect" in result.stderr


def test_remote_localhost_uses_first_free_port_when_preferred_is_taken(monkeypatch: Any) -> None:
    client = load_client()
    monkeypatch.setitem(
        client["allocate_localhost_forward_port"].__globals__,
        "port_available",
        lambda port: port != 18080,
    )
    assert client["allocate_localhost_forward_port"](8080, 18000, 18999) == 18000


def test_remote_localhost_rejects_unallowed_ssh_host() -> None:
    client = load_client()
    with pytest.raises(client["RequestError"], match="ssh_host is not allowed"):
        client["open_remote_localhost"](request(), {"other"}, args())

def test_master_startup_failure_cleans_process_and_private_socket(monkeypatch: Any) -> None:
    client = load_client()

    class PendingMaster:
        terminated = False
        control_path: Path | None = None

        def poll(self) -> int | None:
            return 0 if self.terminated else None

        def terminate(self) -> None:
            self.terminated = True

        def wait(self, timeout: float | None = None) -> int:
            return 0

    process = PendingMaster()

    def launch(command: list[str], **_kwargs: Any) -> PendingMaster:
        process.control_path = Path(command[command.index("-S") + 1])
        assert process.control_path.parent.stat().st_mode & 0o777 == 0o700
        return process

    monkeypatch.setattr(client["subprocess"], "Popen", launch)
    monkeypatch.setitem(client["ensure_remote_localhost_forward"].__globals__, "LOCALHOST_FORWARD_STARTUP_TIMEOUT", 0)
    with pytest.raises(client["RequestError"]):
        client["open_remote_localhost"](request(), {"devbox"}, args(dry_run=False))
    assert process.terminated
    assert process.control_path is not None
    assert not process.control_path.parent.exists()
    assert client["REMOTE_LOCALHOST_FORWARDS"] == {}



def test_remote_localhost_rejects_unknown_remote_host() -> None:
    client = load_client()
    with pytest.raises(client["RequestError"], match="unsupported remote localhost host"):
        client["open_remote_localhost"](request(remote_host="example.com"), {"devbox"}, args())
