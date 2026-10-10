from __future__ import annotations

import http.client
import json
import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import tmux_opener_dashboard as dashboard
from lib.tmux_opener_dashboard import _DashboardServer, client_request, collect_status


class UnixResponder:
    def __init__(self, path: Path, response_factory):
        self.path = path
        self.response_factory = response_factory
        self.requests: list[dict[str, object]] = []
        self.stop = threading.Event()
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(path))
        self.listener.listen()
        self.listener.settimeout(0.1)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while not self.stop.is_set():
            try:
                connection, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                if self.stop.is_set():
                    return
                raise
            with connection:
                frame = connection.recv(1024 * 1024 + 1).split(b"\n", 1)[0]
                request = json.loads(frame)
                self.requests.append(request)
                connection.sendall(json.dumps(self.response_factory(request)).encode() + b"\n")

    def close(self) -> None:
        self.stop.set()
        self.listener.close()
        self.thread.join(timeout=2)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def _http(server: _DashboardServer, method: str, target: str, headers=None, body: bytes | None = None):
    host, port = server.server_address
    connection = http.client.HTTPConnection(host, port, timeout=2)
    connection.request(method, target, body=body, headers=headers or {})
    response = connection.getresponse()
    result = (response.status, dict(response.getheaders()), response.read())
    connection.close()
    return result


def _start_server(tmp_path: Path, token: str = "test-token") -> tuple[_DashboardServer, threading.Thread]:
    state_dir = tmp_path / "state"
    snippet_dir = tmp_path / "snippets"
    state_dir.mkdir(exist_ok=True)
    snippet_dir.mkdir(exist_ok=True)
    server = _DashboardServer(("127.0.0.1", 0), state_dir, snippet_dir, token, None, None)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop_server(server: _DashboardServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_collect_status_includes_configured_offline_hosts(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    snippet_dir = tmp_path / "snippets"
    state_dir.mkdir()
    snippet_dir.mkdir()
    socket_path = state_dir / "online.sock"
    responder = UnixResponder(
        socket_path,
        lambda _request: {
            "ok": True,
            "client_info": {"hostname": "desktop", "user": "alice", "os": "Linux", "pid": 7},
            "hosts": [],
            "downloads": [],
            "remote_localhost_forwards": [],
        },
    )
    offline_socket = state_dir / "offline.sock"
    (snippet_dir / "offline.conf").write_text(
        f"Host offline\n  RemoteForward /tmp/tmux-opener-%r.sock {offline_socket}\n",
        encoding="utf-8",
    )
    try:
        status = collect_status(state_dir, snippet_dir)
    finally:
        responder.close()

    clients = {entry["host"]: entry for entry in status["clients"]}
    assert clients["online"]["online"] is True
    assert clients["online"]["client_info"]["hostname"] == "desktop"
    assert clients["offline"]["online"] is False
    assert clients["offline"]["socket"] == str(offline_socket)
    assert clients["offline"]["error"]
    assert status["updated_at"].endswith("+00:00")


def test_client_request_adds_version_and_returns_transport_error(tmp_path: Path) -> None:
    socket_path = tmp_path / "client.sock"
    responder = UnixResponder(socket_path, lambda request: {"ok": True, "seen": request})
    try:
        response = client_request(socket_path, {"action": "get_status"})
    finally:
        responder.close()
    assert response["ok"] is True
    assert responder.requests == [{"action": "get_status", "version": 1}]
    missing = client_request(tmp_path / "missing.sock", {"action": "get_status"})
    assert missing["ok"] is False
    assert "error" in missing


def test_explicit_host_selects_custom_socket_and_missing_host_is_offline(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    snippet_dir = tmp_path / "snippets"
    state_dir.mkdir()
    snippet_dir.mkdir()
    custom_socket = tmp_path / "socket-with-an-unrelated-name.sock"
    responder = UnixResponder(
        custom_socket,
        lambda _request: {
            "ok": True,
            "client_info": {},
            "hosts": [],
            "downloads": [],
            "remote_localhost_forwards": [],
        },
    )
    try:
        selected = collect_status(state_dir, snippet_dir, host="cluster", socket_path=custom_socket)
        missing = collect_status(state_dir, snippet_dir, host="not-installed")
    finally:
        responder.close()

    assert selected["clients"] == [
        {
            "host": "cluster",
            "socket": str(custom_socket),
            "online": True,
            "error": None,
            "can_restart": False,
            "client_info": {},
            "hosts": [],
            "downloads": [],
            "remote_localhost_forwards": [],
        }
    ]
    assert len(missing["clients"]) == 1
    assert missing["clients"][0]["host"] == "not-installed"
    assert missing["clients"][0]["socket"] == str(state_dir / "not-installed.sock")
    assert missing["clients"][0]["online"] is False


def test_status_schema_rejects_old_and_non_boolean_clients(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    snippet_dir = tmp_path / "snippets"
    state_dir.mkdir()
    snippet_dir.mkdir()
    old_socket = state_dir / "old.sock"
    wrong_socket = state_dir / "wrong.sock"
    old_responder = UnixResponder(old_socket, lambda _request: {"ok": True})
    wrong_responder = UnixResponder(wrong_socket, lambda _request: {"ok": 1})
    try:
        status = collect_status(state_dir, snippet_dir)
    finally:
        old_responder.close()
        wrong_responder.close()

    clients = {entry["host"]: entry for entry in status["clients"]}
    assert clients["old"]["online"] is False
    assert clients["old"]["error"] == "old client unsupported: get_status is unavailable"
    assert clients["wrong"]["online"] is False
    assert clients["wrong"]["error"] == "invalid get_status response: ok must be a boolean"


def test_restart_api_authenticates_owner_and_scopes_bulk_actions(tmp_path: Path) -> None:
    server, thread = _start_server(tmp_path)
    port = server.server_address[1]
    requests = []

    def respond(payload):
        requests.append(payload)
        if payload["action"] == "restart_client":
            return {"ok": True, "restart_accepted": True}
        return {"ok": True, "can_restart": True, "client_info": {"instance_id": "current"},
                "hosts": [], "downloads": [], "remote_localhost_forwards": []}

    path = server.state_dir / "work.sock"
    responder = UnixResponder(path, respond)
    headers = {"Authorization": "Bearer test-token", "Origin": f"http://127.0.0.1:{port}",
               "Content-Type": "application/json"}

    def post(payload, selected_headers=None):
        return _http(server, "POST", "/api/clients", headers if selected_headers is None else selected_headers,
                     json.dumps(payload).encode())

    try:
        payload = {"action": "restart", "socket": str(path), "instance_id": "current"}
        assert post(payload, {})[0] == 401
        assert post({"action": []})[0] == 400
        assert post({**payload, "pid": 123})[0] == 400
        assert post(payload, {**headers, "Origin": "https://untrusted.invalid"})[0] == 403
        assert post({**payload, "socket": str(tmp_path / "outside.sock")})[0] == 403
        assert post({**payload, "instance_id": "old"})[0] == 409
        assert not any(item["action"] == "restart_client" for item in requests)
        assert post(payload)[0] == 200
        assert [item for item in requests if item["action"] == "restart_client"] == [
            {"version": 1, "action": "restart_client", "instance_id": "current"}]
        (server.snippet_dir / "offline.conf").write_text("Host offline\n")
        status, _, body = post({"action": "restart_all"})
        assert status == 200
        assert [entry["host"] for entry in json.loads(body)["results"]] == ["work"]
    finally:
        responder.close()
        _stop_server(server, thread)


def test_status_preserves_history_error_without_arbitrary_response_fields(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    snippet_dir = tmp_path / "snippets"
    state_dir.mkdir()
    snippet_dir.mkdir()
    socket_path = state_dir / "history.sock"
    responder = UnixResponder(
        socket_path,
        lambda _request: {
            "ok": True,
            "client_info": {},
            "hosts": [],
            "downloads": [],
            "remote_localhost_forwards": [],
            "history_error": "history database is temporarily unavailable",
            "unexpected": "must not be exposed",
        },
    )
    try:
        status = collect_status(state_dir, snippet_dir)
    finally:
        responder.close()

    client = status["clients"][0]
    assert client["history_error"] == "history database is temporarily unavailable"
    assert "unexpected" not in client


def test_status_polls_at_most_eight_sockets_concurrently(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    snippet_dir = tmp_path / "snippets"
    state_dir.mkdir()
    snippet_dir.mkdir()
    listeners = []
    for index in range(16):
        path = state_dir / f"host-{index}.sock"
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(path))
        listeners.append(listener)
    active = 0
    maximum = 0
    lock = threading.Lock()

    def fake_request(_path: Path, _request: dict[str, object]):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return {"ok": False, "error": "test"}

    monkeypatch.setattr(dashboard, "client_request", fake_request)
    try:
        status = collect_status(state_dir, snippet_dir)
    finally:
        for listener in listeners:
            listener.close()
    assert len(status["clients"]) == 16
    assert maximum <= 8


def test_status_api_requires_bearer_and_rejects_host_header(tmp_path: Path) -> None:
    server, thread = _start_server(tmp_path)
    port = server.server_address[1]
    try:
        no_auth = _http(server, "GET", "/api/status", {"Host": f"127.0.0.1:{port}"})
        assert no_auth[0] == 401
        wrong_host = _http(
            server,
            "GET",
            "/api/status",
            {"Host": f"attacker.invalid:{port}", "Authorization": "Bearer test-token"},
        )
        assert wrong_host[0] == 421
        status = _http(
            server,
            "GET",
            "/api/status",
            {"Host": f"localhost:{port}", "Authorization": "Bearer test-token"},
        )
        assert status[0] == 200
        assert json.loads(status[2]) == {"clients": [], "updated_at": json.loads(status[2])["updated_at"]}
        assert status[1]["Cache-Control"] == "no-store"
        assert "Access-Control-Allow-Origin" not in status[1]
    finally:
        _stop_server(server, thread)


def test_action_requires_local_origin_and_rejects_arbitrary_socket(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    snippet_dir = tmp_path / "snippets"
    state_dir.mkdir()
    snippet_dir.mkdir()
    socket_path = state_dir / "work.sock"
    responder = UnixResponder(socket_path, lambda request: {"ok": True, "action": request.get("action")})
    server, thread = _start_server(tmp_path, token="action-token")
    port = server.server_address[1]
    body = json.dumps({"socket": str(socket_path), "action": "cancel_download", "download_id": "dl-1"}).encode()
    try:
        missing_origin = _http(
            server,
            "POST",
            "/api/action",
            {
                "Host": f"127.0.0.1:{port}",
                "Authorization": "Bearer action-token",
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
            body,
        )
        assert missing_origin[0] == 403

        arbitrary = json.dumps(
            {"socket": str(tmp_path / "outside.sock"), "action": "cancel_download", "download_id": "dl-1"}
        ).encode()
        rejected = _http(
            server,
            "POST",
            "/api/action",
            {
                "Host": f"127.0.0.1:{port}",
                "Authorization": "Bearer action-token",
                "Origin": f"http://127.0.0.1:{port}",
                "Content-Type": "application/json",
                "Content-Length": str(len(arbitrary)),
            },
            arbitrary,
        )
        assert rejected[0] == 403
        assert all(request["action"] == "get_status" for request in responder.requests)

        accepted = _http(
            server,
            "POST",
            "/api/action",
            {
                "Host": f"127.0.0.1:{port}",
                "Authorization": "Bearer action-token",
                "Origin": f"http://127.0.0.1:{port}",
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
            body,
        )
        assert accepted[0] == 200
        assert responder.requests[0]["action"] == "get_status"
        assert responder.requests[-1]["action"] == "cancel_download"
    finally:
        responder.close()
        _stop_server(server, thread)


def test_settings_api_reads_validates_and_saves(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    server, thread = _start_server(tmp_path, token="settings-token")
    port = server.server_address[1]
    headers = {"Host": f"127.0.0.1:{port}", "Authorization": "Bearer settings-token",
               "Origin": f"http://127.0.0.1:{port}", "Content-Type": "application/json"}

    def post(settings: object, **extra: str):
        body = json.dumps({"settings": settings}).encode()
        return _http(server, "POST", "/api/settings", {**headers, **extra, "Content-Length": str(len(body))}, body)

    try:
        current = json.loads(_http(server, "GET", "/api/settings", headers)[2])
        assert current["settings"]["rules"] == [] and ".pdf" in current["preview_suffixes"]
        assert post({"rules": []}, Origin="http://evil.example")[0] == 403
        assert post({"rules": [{"pattern": "*.pdf", "opener": "open -a Terminal"}]})[0] == 400
        status, _headers, body = post({"rules": [{"pattern": "*.pdf", "opener": "preview"}]})
        assert status == 200
        assert json.loads(body)["settings"]["rules"] == [{"pattern": "*.pdf", "opener": "preview"}]
        saved = json.loads((tmp_path / "config" / "tmux-opener" / "settings.json").read_text())
        assert saved["rules"] == [{"pattern": "*.pdf", "opener": "preview"}]
    finally:
        _stop_server(server, thread)
