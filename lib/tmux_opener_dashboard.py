"""Small, local-only browser dashboard for tmux-opener clients.

The dashboard intentionally has no third-party dependencies.  The HTTP
listener is bound to loopback, and the bearer token is kept in the URL
fragment so it is never sent to the server as part of an HTTP request.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import stat
import time
import urllib.parse
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


MAX_FRAME_BYTES = 1024 * 1024
MAX_ACTION_BYTES = 64 * 1024
DEFAULT_TIMEOUT = 3.0
API_VERSION = 1
ACTION_NAMES = {"cancel_download", "retry_download"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _error_response(message: str) -> dict[str, object]:
    return {"ok": False, "error": message}


def _normalise_path(value: str | os.PathLike[str]) -> str:
    return str(Path(value).expanduser().absolute())


def _socket_path(path: Path) -> bool:
    """Return whether *path* is a socket without following symlinks."""

    try:
        return stat.S_ISSOCK(path.lstat().st_mode)
    except OSError:
        return False


def _read_snippet_socket(path: Path) -> str | None:
    """Read the local socket from a managed SSH snippet, if it has one."""

    try:
        lines = path.read_text(encoding="utf-8", errors="strict").splitlines()
    except (OSError, UnicodeError):
        return None
    for line in lines:
        fields = line.split()
        if len(fields) < 3 or fields[0].lower() != "remoteforward":
            continue
        local = fields[2]
        if "\x00" in local or "\r" in local or "\n" in local:
            continue
        return _normalise_path(local)
    return None


def _configured_sockets(snippet_dir: Path, state_dir: Path) -> dict[str, str]:
    """Return configured host -> local socket path mappings.

    A snippet without a parseable managed forward still describes a configured
    host; its normal state-directory socket is used as a useful fallback.
    """

    configured: dict[str, str] = {}
    try:
        snippets = sorted(snippet_dir.glob("*.conf"), key=lambda p: p.name)
    except OSError:
        snippets = []
    for snippet in snippets:
        try:
            info = snippet.lstat()
        except OSError:
            continue
        if not stat.S_ISREG(info.st_mode):
            continue
        host = snippet.stem
        if not host:
            continue
        configured[host] = _read_snippet_socket(snippet) or _normalise_path(state_dir / f"{host}.sock")
    return configured


def _candidate_sockets(state_dir: Path, snippet_dir: Path) -> list[tuple[str, str]]:
    """Discover socket files and configured offline hosts."""

    configured = _configured_sockets(snippet_dir, state_dir)
    # Mapping by path lets a managed snippet give a socket a more useful host
    # label than an opaque filename.  A deterministic first label wins.
    path_hosts: dict[str, str] = {}
    for host, path in configured.items():
        path_hosts.setdefault(path, host)

    candidates: dict[str, str] = {}
    try:
        state_entries = sorted(state_dir.glob("*.sock"), key=lambda p: p.name)
    except OSError:
        state_entries = []
    for path in state_entries:
        if not _socket_path(path):
            continue
        normal = _normalise_path(path)
        candidates[normal] = path_hosts.get(normal, path.stem)

    # A configured socket can live outside state_dir.  Include it when it is a
    # real socket; absent configured sockets are retained as offline entries.
    for host, path in configured.items():
        candidates.setdefault(path, host)
    return sorted(((host, path) for path, host in candidates.items()), key=lambda item: (item[0], item[1]))


def _status_entry(host: str, path: str, response: dict[str, object]) -> dict[str, object]:
    ok = response.get("ok")
    if type(ok) is not bool:
        online = False
        error = "invalid get_status response: ok must be a boolean"
    elif not ok:
        online = False
        error = str(response.get("error") or "client did not acknowledge status")
    elif not (
        isinstance(response.get("client_info"), dict)
        and isinstance(response.get("hosts"), list)
        and isinstance(response.get("downloads"), list)
        and isinstance(response.get("remote_localhost_forwards"), list)
    ):
        online = False
        error = "old client unsupported: get_status is unavailable"
    else:
        online = True
        error = None
    entry: dict[str, object] = {
        "host": host,
        "socket": path,
        "online": online,
        "error": error,
        "client_info": response.get("client_info") if isinstance(response.get("client_info"), dict) else {},
        "hosts": response.get("hosts") if isinstance(response.get("hosts"), list) else [],
        "downloads": response.get("downloads") if isinstance(response.get("downloads"), list) else [],
        "remote_localhost_forwards": (
            response.get("remote_localhost_forwards")
            if isinstance(response.get("remote_localhost_forwards"), list)
            else []
        ),
    }
    if isinstance(response.get("history_error"), str):
        entry["history_error"] = response["history_error"]
    return entry


def client_request(socket_path: Path, request: dict[str, object], timeout: float = DEFAULT_TIMEOUT) -> dict[str, object]:
    """Send one bounded JSON-line request to a local client socket.

    Transport and protocol failures are returned as ``{"ok": False, ...}``
    so the status page can keep showing healthy clients when one is stale.
    """

    if not isinstance(request, dict):
        return _error_response("request must be an object")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        return _error_response("invalid request timeout")
    payload = dict(request)
    payload["version"] = API_VERSION
    try:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return _error_response("request is not JSON serialisable")
    if len(encoded) > MAX_FRAME_BYTES:
        return _error_response("request is too large")

    path = Path(socket_path).expanduser()
    if not _socket_path(path):
        return _error_response("client socket is unavailable")
    deadline = time.monotonic() + float(timeout)
    frame = bytearray()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            peer.settimeout(remaining)
            peer.connect(str(path))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            peer.settimeout(remaining)
            peer.sendall(encoded)
            while b"\n" not in frame:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                peer.settimeout(remaining)
                chunk = peer.recv(min(65536, MAX_FRAME_BYTES + 1 - len(frame)))
                if not chunk:
                    raise ValueError("client closed before its response")
                frame.extend(chunk)
                if len(frame) > MAX_FRAME_BYTES:
                    raise ValueError("client response is too large")
    except (OSError, TimeoutError, ValueError) as exc:
        if isinstance(exc, TimeoutError) or isinstance(exc, socket.timeout):
            return _error_response("client request timed out")
        return _error_response(str(exc) or "client request failed")

    first_line = bytes(frame).split(b"\n", 1)[0]
    try:
        parsed = json.loads(first_line.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return _error_response("client returned invalid JSON")
    if not isinstance(parsed, dict):
        return _error_response("client response must be an object")
    return parsed


def collect_status(
    state_dir: Path,
    snippet_dir: Path,
    host: str | None = None,
    socket_path: Path | None = None,
) -> dict[str, object]:
    """Collect a stable, JSON-ready snapshot of configured local clients."""

    state_dir = Path(state_dir).expanduser()
    snippet_dir = Path(snippet_dir).expanduser()
    selected_socket = _normalise_path(socket_path) if socket_path is not None else None
    candidates = _candidate_sockets(state_dir, snippet_dir)
    if selected_socket is not None:
        # An explicitly supplied socket is an intentional selection even when
        # it lives outside the usual state directory.  A supplied host is its
        # alias, independent of the custom socket filename.
        selected_host = host
        if selected_host is None:
            selected_host = next((candidate_host for candidate_host, path in candidates if path == selected_socket), None)
        candidates = [(selected_host or Path(selected_socket).stem, selected_socket)]
    elif host is not None:
        matching = [(candidate_host, path) for candidate_host, path in candidates if candidate_host == host]
        # Keep an explicitly requested configured host visible when its socket
        # is absent or was never installed.
        candidates = matching or [(host, _normalise_path(state_dir / f"{host}.sock"))]

    def poll(candidate: tuple[str, str]) -> tuple[str, str, dict[str, object]]:
        candidate_host, candidate_path = candidate
        try:
            response = client_request(Path(candidate_path), {"action": "get_status"})
        except Exception as exc:  # defensive boundary for a status worker
            response = _error_response(str(exc) or "client request failed")
        return candidate_host, candidate_path, response

    if not candidates:
        return {"clients": [], "updated_at": _utc_now()}
    with ThreadPoolExecutor(max_workers=min(8, len(candidates))) as executor:
        polled = list(executor.map(poll, candidates))
    entries = [_status_entry(candidate_host, candidate_path, response) for candidate_host, candidate_path, response in polled]
    return {"clients": entries, "updated_at": _utc_now()}


class _DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(
        self,
        server_address: tuple[str, int],
        state_dir: Path,
        snippet_dir: Path,
        token: str,
        host_filter: str | None,
        socket_filter: Path | None,
    ) -> None:
        self.state_dir = Path(state_dir).expanduser()
        self.snippet_dir = Path(snippet_dir).expanduser()
        self.token = token
        self.host_filter = host_filter
        self.socket_filter = socket_filter
        super().__init__(server_address, _DashboardHandler)


class _DashboardHandler(BaseHTTPRequestHandler):
    server: _DashboardServer

    # The default handler logs the complete request target, which would leak
    # URL query strings if a future route accidentally accepted the fragment
    # token in the wrong place.  Dashboard requests are deliberately silent.
    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _send_json(self, payload: dict[str, object], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: int, message: str) -> None:
        self._send_json({"ok": False, "error": message}, status)

    def _host_is_local(self) -> bool:
        raw = self.headers.get("Host", "")
        try:
            parsed = urllib.parse.urlsplit("//" + raw)
            port = parsed.port
        except ValueError:
            return False
        return (
            parsed.hostname in {"localhost", "127.0.0.1"}
            and port == self.server.server_address[1]
            and not parsed.username
            and not parsed.password
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
        )

    def _origin_is_local(self) -> bool:
        raw = self.headers.get("Origin")
        if not raw:
            return False
        try:
            parsed = urllib.parse.urlsplit(raw)
            port = parsed.port
        except ValueError:
            return False
        return (
            parsed.scheme == "http"
            and parsed.hostname in {"localhost", "127.0.0.1"}
            and port == self.server.server_address[1]
            and not parsed.username
            and not parsed.password
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
        )

    def _authorised(self) -> bool:
        value = self.headers.get("Authorization", "")
        scheme, separator, supplied = value.partition(" ")
        return separator == " " and scheme.lower() == "bearer" and secrets.compare_digest(supplied, self.server.token)

    def _api_guard(self, require_origin: bool = False) -> bool:
        if not self._host_is_local():
            self._send_error_json(HTTPStatus.MISDIRECTED_REQUEST, "request host is not allowed")
            return False
        if not self._authorised():
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.send_header("WWW-Authenticate", "Bearer")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return False
        if require_origin and not self._origin_is_local():
            self._send_error_json(HTTPStatus.FORBIDDEN, "request origin is not allowed")
            return False
        return True

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if not self._host_is_local():
            self._send_error_json(HTTPStatus.MISDIRECTED_REQUEST, "request host is not allowed")
            return
        route = urllib.parse.urlsplit(self.path)
        if route.path == "/api/status":
            if not self._api_guard():
                return
            self._send_json(
                collect_status(
                    self.server.state_dir,
                    self.server.snippet_dir,
                    self.server.host_filter,
                    self.server.socket_filter,
                )
            )
            return
        if route.path not in {"/", "/dashboard.html"}:
            self._send_error_json(HTTPStatus.NOT_FOUND, "not found")
            return
        try:
            body = (Path(__file__).with_name("dashboard.html")).read_bytes()
        except OSError:
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "dashboard asset unavailable")
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_action(self) -> dict[str, object] | None:
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length) if raw_length is not None else -1
        except ValueError:
            length = -1
        if length < 0 or length > MAX_ACTION_BYTES:
            self._send_error_json(HTTPStatus.BAD_REQUEST, "invalid request body")
            return None
        try:
            raw = self.rfile.read(length)
            parsed = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, ValueError, RecursionError):
            self._send_error_json(HTTPStatus.BAD_REQUEST, "request body must be JSON")
            return None
        if not isinstance(parsed, dict):
            self._send_error_json(HTTPStatus.BAD_REQUEST, "request body must be an object")
            return None
        return parsed

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        if not self._host_is_local():
            self._send_error_json(HTTPStatus.MISDIRECTED_REQUEST, "request host is not allowed")
            return
        route = urllib.parse.urlsplit(self.path)
        if route.path != "/api/action":
            self._send_error_json(HTTPStatus.NOT_FOUND, "not found")
            return
        if not self._api_guard(require_origin=True):
            return
        payload = self._read_action()
        if payload is None:
            return
        if set(payload) != {"socket", "action", "download_id"}:
            self._send_error_json(HTTPStatus.BAD_REQUEST, "unsupported action fields")
            return
        requested_socket = payload.get("socket")
        action = payload.get("action")
        download_id = payload.get("download_id")
        if not isinstance(requested_socket, str) or not isinstance(action, str) or not isinstance(download_id, str):
            self._send_error_json(HTTPStatus.BAD_REQUEST, "socket, action and download_id must be strings")
            return
        if action not in ACTION_NAMES or not download_id or len(download_id) > 4096 or "\x00" in download_id:
            self._send_error_json(HTTPStatus.BAD_REQUEST, "unsupported download action")
            return
        canonical_socket = _normalise_path(requested_socket)
        selected = collect_status(
            self.server.state_dir,
            self.server.snippet_dir,
            self.server.host_filter,
            self.server.socket_filter,
        )
        allowed = {
            item.get("socket")
            for item in selected.get("clients", [])
            if isinstance(item, dict) and isinstance(item.get("socket"), str)
        }
        if canonical_socket not in allowed:
            self._send_error_json(HTTPStatus.FORBIDDEN, "socket is not a discovered client")
            return
        response = client_request(
            Path(canonical_socket),
            {"action": action, "download_id": download_id},
        )
        self._send_json(response, HTTPStatus.OK if response.get("ok") is True else HTTPStatus.BAD_GATEWAY)


def _dashboard_url(server: _DashboardServer, token: str) -> str:
    port = server.server_address[1]
    return f"http://127.0.0.1:{port}/#token={urllib.parse.quote(token, safe='')}"


def run_dashboard(
    state_dir: Path,
    snippet_dir: Path,
    host: str | None = None,
    socket_path: Path | None = None,
    no_browser: bool = False,
) -> int:
    """Run the loopback dashboard until Ctrl-C and return a process code."""

    token = secrets.token_urlsafe(32)
    server = _DashboardServer(("127.0.0.1", 0), state_dir, snippet_dir, token, host, socket_path)
    url = _dashboard_url(server, token)
    print(url, flush=True)
    if not no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            # Opening a browser is a convenience; the printed URL remains
            # usable when a desktop opener is unavailable.
            pass
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        return 0
    finally:
        server.shutdown()
        server.server_close()
    return 0


__all__ = ["client_request", "collect_status", "run_dashboard"]
