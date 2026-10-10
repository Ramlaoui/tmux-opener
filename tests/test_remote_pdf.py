from __future__ import annotations

import json
import os
import runpy
import shlex
import subprocess
import sys
import time
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def preview(tmp_path, monkeypatch):
    client = runpy.run_path(str(ROOT / "bin/tmux-opener-client"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    calls = []
    state = {"pdf": b"%PDF-1.7\nfirst build", "returncode": 0}

    def transfer(command, **kwargs):
        if command[0] == "osascript":
            calls.append(("reload", command))
            return SimpleNamespace(returncode=state.get("reload_returncode", 0), stderr=b"reload failed")
        calls.append(("transfer", command))
        kwargs["stdout"].write(state["pdf"])
        return SimpleNamespace(returncode=state["returncode"], stderr=b"transfer failed")

    def launch(command, *args):
        calls.append(("viewer", command))
        return SimpleNamespace(poll=lambda: None)

    monkeypatch.setattr(client["subprocess"], "run", transfer)
    monkeypatch.setitem(client["open_remote_pdf"].__globals__, "launch_command", launch)
    args = Namespace(dry_run=False, verbose=False, ssh_config=None, pdf_viewer="zathura",
                     default_ssh_host="devbox", allow_ssh_host=["devbox"], allow_any_ssh_host=False)
    request = {"version": 1, "action": "open_remote_pdf", "path": "/paper/my '$(touch nope)' paper.pdf"}
    return client, args, request, calls, state, tmp_path


def test_pdf_opens_once_and_refresh_replaces_same_path(preview):
    client, args, request, calls, state, cache = preview
    client["dispatch"](request, args)
    local_pdf = next(cache.rglob("document.pdf"))
    assert local_pdf.read_bytes() == state["pdf"]
    transfer_command = calls[0][1]
    assert shlex.split(transfer_command[-1]) == ["test", "-f", request["path"], "&&", "cat", "--", request["path"]]
    assert "ClearAllForwardings=yes" in transfer_command
    assert "BatchMode=yes" in transfer_command
    assert transfer_command[transfer_command.index("-S") + 1] == "none"
    assert "PermitLocalCommand=no" in transfer_command
    assert calls[1] == ("viewer", ["zathura", str(local_pdf)])

    original_inode = local_pdf.stat().st_ino
    state["pdf"] = b"%PDF-1.7\nsecond build"
    client["dispatch"]({**request, "refresh": True}, args)
    assert local_pdf.read_bytes() == state["pdf"]
    assert local_pdf.stat().st_ino != original_inode
    assert len([call for call in calls if call[0] == "viewer"]) == 1
    assert list(local_pdf.parent.iterdir()) == [local_pdf]

    unchanged = local_pdf.stat()
    client["dispatch"]({**request, "refresh": True}, args)
    assert local_pdf.stat().st_ino == unchanged.st_ino
    assert local_pdf.stat().st_mtime_ns == unchanged.st_mtime_ns
    client["dispatch"](request, args)
    assert len([call for call in calls if call[0] == "viewer"]) == 1


@pytest.mark.parametrize("failure", ["ssh", "header", "timeout"])
def test_failed_refresh_preserves_previous_pdf(preview, monkeypatch, failure):
    client, args, request, calls, state, cache = preview
    client["dispatch"](request, args)
    local_pdf = next(cache.rglob("document.pdf"))
    previous = local_pdf.read_bytes()
    if failure == "ssh":
        state.update(pdf=b"%PDF-partial", returncode=255)
    elif failure == "header":
        state["pdf"] = b"not a PDF"
    else:
        def timeout(*args, **kwargs):
            kwargs["stdout"].write(b"partial")
            raise subprocess.TimeoutExpired("ssh", 20)
        monkeypatch.setattr(client["subprocess"], "run", timeout)
    with pytest.raises(client["RequestError"], match="PDF transfer failed|PDF header"):
        client["dispatch"]({**request, "refresh": True}, args)
    assert local_pdf.read_bytes() == previous
    assert list(local_pdf.parent.iterdir()) == [local_pdf]
    assert len([call for call in calls if call[0] == "viewer"]) == 1


def test_refresh_before_view_does_nothing(preview):
    client, args, request, calls, _, cache = preview
    client["dispatch"]({**request, "refresh": True}, args)
    assert calls == []
    assert list(cache.iterdir()) == []


def test_skim_refresh_reloads_matching_document_without_opening_window(preview):
    client, args, request, calls, state, cache = preview
    args.pdf_viewer = "skim"
    client["dispatch"](request, args)
    local_pdf = next(cache.rglob("document.pdf"))
    state["pdf"] = b"%PDF-1.7\nsecond build"
    client["dispatch"]({**request, "refresh": True}, args)
    assert local_pdf.read_bytes() == state["pdf"]
    assert len([call for call in calls if call[0] == "viewer"]) == 1
    reload = [call for call in calls if call[0] == "reload"]
    assert len(reload) == 1
    assert reload[0][1][-1] == str(local_pdf)
    script = reload[0][1][2]
    assert 'documents whose path is (item 1 of argv)' in script
    assert "revert pdfDocument" in script
    assert "modified of pdfDocument" in script
    assert "activate" not in script
    assert "open " not in script


def test_skim_reload_error_is_reported_and_can_be_retried(preview):
    client, args, request, calls, state, cache = preview
    args.pdf_viewer = "skim"
    client["dispatch"](request, args)
    state.update(pdf=b"%PDF-1.7\nsecond build", reload_returncode=1)
    with pytest.raises(client["RequestError"], match="Skim reload failed"):
        client["dispatch"]({**request, "refresh": True}, args)
    assert next(cache.rglob("document.pdf")).read_bytes() == state["pdf"]
    state["reload_returncode"] = 0
    client["dispatch"]({**request, "refresh": True}, args)
    assert len([call for call in calls if call[0] == "reload"]) == 2
    assert len([call for call in calls if call[0] == "viewer"]) == 1


def test_auto_viewer_on_mac_reloads_skim(preview, monkeypatch):
    client, args, request, calls, _, _ = preview
    args.pdf_viewer = "auto"
    monkeypatch.setattr(client["platform"], "system", lambda: "Darwin")
    is_directory = Path.is_dir
    monkeypatch.setattr(Path, "is_dir", lambda path: str(path) == "/Applications/Skim.app" or is_directory(path))
    client["dispatch"](request, args)
    client["dispatch"]({**request, "refresh": True}, args)
    assert calls[1][1][:3] == ["open", "-a", "Skim"]
    assert len([call for call in calls if call[0] == "reload"]) == 1


@pytest.mark.parametrize("backend", ["launchd", "systemd-user"])
def test_service_captures_pdf_viewer_preference(tmp_path, monkeypatch, backend):
    wrapper = runpy.run_path(str(ROOT / "bin/tmux-opener"))
    monkeypatch.setenv("TMUX_OPENER_PDF_VIEWER", "system")
    args = wrapper["build_parser"]().parse_args(["install-service", "devbox", "--dry-run"])
    content = wrapper["service_content"](args, "devbox", tmp_path / "devbox.sock", backend)
    assert "--pdf-viewer" in content
    assert "system" in content


def test_pdf_rejects_unallowed_host(preview):
    client, args, request, calls, _, _ = preview
    with pytest.raises(client["RequestError"], match="ssh_host is not allowed"):
        client["dispatch"]({**request, "ssh_host": "other"}, args)
    assert calls == []


def test_sender_pdf_request_handles_spaces_and_quotes(tmp_path):
    pdf = tmp_path / "my 'quoted' paper.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/tmux-opener-send"),
                             "--pdf", "--refresh", "--print-request", str(pdf)],
                            capture_output=True, text=True, check=True)
    request = json.loads(result.stdout)
    assert request["action"] == "open_remote_pdf"
    assert request["path"] == str(pdf)
    assert request["refresh"] is True


def test_live_bridge_opens_and_updates_pdf(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    ssh = fake_bin / "ssh"
    ssh.write_text('#!/bin/sh\nfor arg do command=$arg; done\nexec sh -c "$command"\n')
    viewer = fake_bin / "zathura"
    opened = tmp_path / "opened"
    viewer.write_text('#!/bin/sh\nprintf "%s\\n%s\\n" "$$" "$1" >> '
                      + shlex.quote(str(opened)) + '\nexec sleep 30\n')
    ssh.chmod(0o755)
    viewer.chmod(0o755)
    socket_path = tmp_path / "client.sock"
    pdf = tmp_path / "remote paper.pdf"
    pdf.write_bytes(b"%PDF-1.7\nfirst build")
    env = {**os.environ, "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
           "XDG_CACHE_HOME": str(tmp_path / "cache")}
    client = subprocess.Popen([sys.executable, str(ROOT / "bin/tmux-opener-client"),
                               "--socket", str(socket_path), "--default-ssh-host", "devbox",
                               "--allow-ssh-host", "devbox", "--pdf-viewer", "zathura"],
                              env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    sender = [sys.executable, str(ROOT / "scripts/tmux-opener-send"), "--socket", str(socket_path), "--no-log"]
    try:
        deadline = time.monotonic() + 3
        while not socket_path.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        subprocess.run([*sender, "--pdf", "--check-bridge"], env=env, check=True, timeout=5)
        subprocess.run([*sender, "--pdf", str(pdf)], env=env, check=True, timeout=5)
        while not opened.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        _, local_path = opened.read_text().splitlines()
        assert Path(local_path).read_bytes() == pdf.read_bytes()
        pdf.write_bytes(b"%PDF-1.7\nsecond build")
        subprocess.run([*sender, "--pdf", "--refresh", str(pdf)], env=env, check=True, timeout=5)
        assert Path(local_path).read_bytes() == pdf.read_bytes()
        assert len(opened.read_text().splitlines()) == 2
    finally:
        client.terminate()
        client.wait(timeout=3)
        if opened.exists():
            for pid in opened.read_text().splitlines()[::2]:
                os.kill(int(pid), 15)
