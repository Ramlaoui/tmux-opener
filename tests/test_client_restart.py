from __future__ import annotations

import json
import os
import runpy
import socket
import subprocess
import sys
import time
from argparse import Namespace
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def request(path: Path, payload: dict) -> dict:
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(1)
        connection.connect(str(path))
        connection.sendall(json.dumps({"version": 1, **payload}).encode() + b"\n")
        return json.loads(connection.makefile("rb").readline())


def wait_for_instance(path: Path, previous: str | None = None) -> dict:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            response = request(path, {"action": "ping"})
            if response.get("ok") and response["instance_id"] != previous:
                return response
        except (OSError, ValueError):
            pass
        time.sleep(0.05)
    raise AssertionError("client did not become ready with a new instance")


def test_restart_acknowledges_then_reexecs_same_owner_and_preserves_options(tmp_path):
    path = tmp_path / "client.sock"
    config = tmp_path / "ssh-config"
    config.write_text("")
    process = subprocess.Popen([
        sys.executable, str(ROOT / "bin/tmux-opener-client"), "--socket", str(path),
        "--allow-ssh-host", "first", "--allow-ssh-host", "second", "--ssh-config", str(config),
        "--pdf-viewer", "system", "--vscode-file-window", "reuse",
    ], env={**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "config")},
       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        initial = wait_for_instance(path)
        rejected = request(path, {"action": "restart_client", "instance_id": "old-instance"})
        assert rejected["ok"] is False
        assert request(path, {"action": "ping"})["instance_id"] == initial["instance_id"]
        accepted = request(path, {"action": "restart_client", "instance_id": initial["instance_id"]})
        assert accepted == {"ok": True, "restart_accepted": True}
        restarted = wait_for_instance(path, initial["instance_id"])
        assert restarted["pid"] == initial["pid"] == process.pid
        assert restarted["allowed_ssh_hosts"] == ["first", "second"]
        assert request(path, {"action": "get_status"})["can_restart"] is True
        assert process.poll() is None
    finally:
        process.terminate()
        process.wait(timeout=8)
    assert not path.exists()


@pytest.mark.parametrize("once,dry_run", [(True, False), (False, True)])
def test_preview_clients_cannot_restart(once, dry_run):
    client = runpy.run_path(str(ROOT / "bin/tmux-opener-client"))
    args = Namespace(once=once, dry_run=dry_run, verbose=False)
    with pytest.raises(client["RequestError"], match="cannot restart"):
        client["dispatch"]({"action": "restart_client", "instance_id": client["INSTANCE_ID"]}, args)
