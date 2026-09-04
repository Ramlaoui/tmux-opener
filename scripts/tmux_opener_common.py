"""Shared helpers for tmux-opener remote-side scripts."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path


URL_RE = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*://|mailto:)")
URL_WHITESPACE_RE = re.compile(r"\s+")
URL_LINE_BORDER_RE = re.compile(r"^\s*[|│┃║]+\s*|\s*[|│┃║]+\s*$")
LOCALHOST_TOKEN_RE = re.compile(
    r"^(?:(?P<scheme>https?)://)?"
    r"(?P<host>localhost|127\.0\.0\.1|0\.0\.0\.0)"
    r":(?P<port>[1-9][0-9]{0,4})"
    r"(?P<tail>[/?#]\S*)?$"
)
LINE_RE = re.compile(r"^(?P<path>.*?)(?::(?P<line>[1-9][0-9]*))(?::(?P<column>[1-9][0-9]*))?$")
PYTHON_TRACEBACK_RE = re.compile(
    r"\bFile\s+(?P<quote>[\"'])(?P<path>.*?)(?P=quote),\s+line\s+(?P<line>[1-9][0-9]*)"
)
PYTEST_RESULT_RE = re.compile(r"^\s*(?:FAILED|ERROR)\s+(?P<target>\S+)")
QUOTED_CANDIDATE_RE = re.compile(r"(?P<quote>[\"'`])(?P<value>.*?)(?P=quote)")
PATH_LINE_CANDIDATE_RE = re.compile(r"(?P<candidate>\S+?:[1-9][0-9]*(?::[1-9][0-9]*)?:?)")
TOKEN_RE = re.compile(r"\S+")
WRAPPED_PATH_FRAGMENT_RE = re.compile(r"^[^\s]+$")

WRAPPER_PAIRS = {
    "(": ")",
    "[": "]",
    "{": "}",
    "<": ">",
}
PATH_LEADING_PUNCTUATION = "\"'`([{<"
PATH_TRAILING_PUNCTUATION = "\"'`)]}>.,;:"


def default_socket_path() -> str:
    if value := os.environ.get("TMUX_OPENER_SOCKET"):
        return os.path.expanduser(value)
    user = os.environ.get("USER") or "user"
    return f"/tmp/tmux-opener-{user}.sock"


def default_log_path() -> str:
    if value := os.environ.get("TMUX_OPENER_LOG"):
        return os.path.expanduser(value)
    return os.path.expanduser("~/.local/state/tmux-opener/sender.log")


def log_line(log_path: str | None, message: str) -> None:
    if not log_path:
        return

    try:
        path = Path(log_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().isoformat(timespec="seconds")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} {message}\n")
    except OSError:
        pass


def describe_request(request: dict[str, object]) -> str:
    action = str(request.get("action", "unknown"))
    if action == "open_url":
        return f"action=open_url url={request.get('url')}"
    if action == "open_remote_localhost":
        return (
            "action=open_remote_localhost "
            f"host={request.get('ssh_host', 'default')} "
            f"remote_port={request.get('remote_port')}"
        )
    if action == "open_vscode_remote":
        return (
            "action=open_vscode_remote "
            f"type={request.get('target_type', 'file')} "
            f"path={request.get('path')}"
        )
    return f"action={action}"


def default_ssh_host() -> str | None:
    for key in ("TMUX_OPENER_SSH_HOST", "VSCODE_SSH_HOST"):
        if value := os.environ.get(key):
            return value
    return None


def clean_selection(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'`":
        text = text[1:-1]
    return text.strip(" \t\r\n")


def is_open_url(text: str) -> bool:
    return URL_RE.match(text) is not None and not text.startswith("file:")


def parse_remote_localhost(text: str) -> dict[str, object] | None:
    text = strip_wrapping_punctuation(clean_selection(text))
    match = LOCALHOST_TOKEN_RE.match(text)
    if not match:
        return None

    port = int(match.group("port"))
    if not 1 <= port <= 65535:
        return None

    scheme = match.group("scheme") or "http"
    host = match.group("host")
    remote_host = "127.0.0.1" if host == "0.0.0.0" else host
    url = text if match.group("scheme") else f"{scheme}://{text}"
    parsed = urllib.parse.urlparse(url)

    return {
        "scheme": scheme,
        "remote_host": remote_host,
        "remote_port": port,
        "path": parsed.path or "",
        "query": parsed.query or "",
        "fragment": parsed.fragment or "",
    }


def strip_wrapping_punctuation(text: str) -> str:
    text = text.strip()
    previous = None
    while text and text != previous:
        previous = text

        if len(text) >= 2 and text[0] in "\"'`" and text[-1] == text[0]:
            text = text[1:-1].strip()
            continue

        if len(text) >= 2 and WRAPPER_PAIRS.get(text[0]) == text[-1]:
            text = text[1:-1].strip()
            continue

        if text and text[0] in PATH_LEADING_PUNCTUATION:
            text = text[1:].strip()
            continue

        if text and text[-1] in PATH_TRAILING_PUNCTUATION:
            text = text[:-1].strip()

    return text


def parse_file_uri(text: str) -> str | None:
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme != "file":
        return None
    return urllib.parse.unquote(parsed.path)


def split_line_column(text: str) -> tuple[str, int | None, int | None]:
    match = LINE_RE.match(text)
    if not match:
        return text, None, None

    path = match.group("path")
    line = int(match.group("line")) if match.group("line") else None
    column = int(match.group("column")) if match.group("column") else None

    if line is None:
        return text, None, None
    return path, line, column


def looks_like_path(text: str) -> bool:
    if not text:
        return False
    if text.startswith(("/", "~/", "./", "../")):
        return True
    return "/" in text


def path_for_candidate(text: str, cwd: str) -> Path | None:
    if file_path := parse_file_uri(text):
        text = file_path

    path_text, _line, _column = split_line_column(text)
    path_text = path_text.strip()
    if not path_text or "\n" in path_text or "\r" in path_text:
        return None

    if not looks_like_path(path_text):
        return Path(cwd, path_text)

    candidate = Path(os.path.expanduser(path_text))
    if not candidate.is_absolute():
        candidate = Path(cwd, candidate)
    return candidate


def existing_path_candidate(text: str, cwd: str) -> bool:
    path = path_for_candidate(text, cwd)
    if path is None:
        return False
    try:
        return path.exists()
    except OSError:
        return False


def path_fragment(text: str) -> str:
    return strip_wrapping_punctuation(text).strip()


def can_join_wrapped_path_fragment(left: str, right: str) -> bool:
    left = path_fragment(left)
    right = path_fragment(right)
    if not left or not right:
        return False
    if not WRAPPED_PATH_FRAGMENT_RE.match(left) or not WRAPPED_PATH_FRAGMENT_RE.match(right):
        return False
    if is_open_url(left) or is_open_url(right):
        return False
    if right.startswith(("/", "~/", "./", "../")):
        return False
    if left.endswith(("/", "\\")):
        return True
    return looks_like_path(left)


def wrapped_path_candidates(text: str, cwd: str) -> list[str]:
    lines = [path_fragment(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    candidates: list[str] = []
    seen: set[str] = set()

    for start in range(len(lines) - 1):
        joined = lines[start]
        for line in lines[start + 1 :]:
            if not can_join_wrapped_path_fragment(joined, line):
                break
            joined = f"{joined}{line}"
            if joined in seen:
                continue
            if looks_like_path(split_line_column(joined)[0]) and existing_path_candidate(joined, cwd):
                candidates.append(joined)
                seen.add(joined)

    return candidates


def candidate_variants(text: str) -> list[str]:
    variants = []
    seen = set()

    def append(value: str) -> None:
        value = value.strip()
        if value and value not in seen:
            variants.append(value)
            seen.add(value)

    raw = text.strip()
    stripped = strip_wrapping_punctuation(text)
    bases = [stripped]
    if raw != stripped:
        bases.append(raw)

    for value in bases:
        if "::" in value:
            append(value.split("::", 1)[0])
            append(strip_wrapping_punctuation(value.split("::", 1)[0]))
        append(value)

    return variants


def normalize_url_candidate(text: str) -> str | None:
    """Return a URL candidate with copy-mode soft-wrap whitespace removed."""
    for variant in candidate_variants(text):
        variant = "\n".join(URL_LINE_BORDER_RE.sub("", line) for line in variant.splitlines())
        if not is_open_url(variant):
            continue

        normalized = URL_WHITESPACE_RE.sub("", variant)
        if is_open_url(normalized) and not any(border in normalized for border in "|│┃║"):
            return normalized

    return None


def resolve_path_candidate(text: str, cwd: str) -> tuple[str, str, int | None, int | None] | None:
    if is_open_url(text):
        return None

    path_text, line, column = split_line_column(text)
    path_text = path_text.strip()
    if not path_text or "\n" in path_text or "\r" in path_text:
        return None

    candidate = path_for_candidate(text, cwd)
    if candidate is None:
        return None

    if not looks_like_path(path_text) and not candidate.exists():
        return None
    if looks_like_path(path_text) and any(character.isspace() for character in path_text) and not candidate.exists():
        return None

    target_type = "folder" if candidate.is_dir() else "file"
    return str(candidate.resolve(strict=False)), target_type, line, column


def valid_file_target(text: str, cwd: str) -> str | None:
    for variant in candidate_variants(text):
        if resolve_path_candidate(variant, cwd) is not None:
            return variant
    return None


def promising_token(text: str) -> bool:
    text = strip_wrapping_punctuation(text)
    if not text:
        return False
    if text.startswith("file:") or "::" in text:
        return True
    path_text, line, _column = split_line_column(text)
    return line is not None or looks_like_path(path_text) or "." in path_text


def file_target_candidates(text: str) -> list[str]:
    candidates = [text]

    traceback_matches = list(PYTHON_TRACEBACK_RE.finditer(text))
    for match in reversed(traceback_matches):
        candidates.append(f"{match.group('path')}:{match.group('line')}")

    for line in text.splitlines():
        if match := PYTEST_RESULT_RE.match(line):
            candidates.append(match.group("target"))

    for match in PATH_LINE_CANDIDATE_RE.finditer(text):
        candidates.append(match.group("candidate"))

    for match in QUOTED_CANDIDATE_RE.finditer(text):
        candidates.append(match.group("value"))

    for match in TOKEN_RE.finditer(text):
        token = match.group(0)
        if promising_token(token):
            candidates.append(token)

    return candidates


def extract_file_target(text: str, cwd: str) -> str | None:
    for candidate in wrapped_path_candidates(clean_selection(text), cwd):
        if target := valid_file_target(candidate, cwd):
            return target

    for candidate in file_target_candidates(clean_selection(text)):
        if target := valid_file_target(candidate, cwd):
            return target
    return None


def extract_target(text: str, cwd: str) -> str | None:
    text = clean_selection(text)
    if parse_remote_localhost(text):
        return text

    if url := normalize_url_candidate(text):
        return url

    return extract_file_target(text, cwd)


def resolve_path(text: str, cwd: str) -> tuple[str, str, int | None, int | None] | None:
    if target := extract_file_target(text, cwd):
        return resolve_path_candidate(target, cwd)
    return None


def build_request(selection: str, cwd: str, ssh_host: str | None) -> dict[str, object] | None:
    target = extract_target(selection, cwd)
    if not target:
        return None

    if remote_localhost := parse_remote_localhost(target):
        request: dict[str, object] = {
            "version": 1,
            "action": "open_remote_localhost",
            **remote_localhost,
        }
        if ssh_host:
            request["ssh_host"] = ssh_host
        return request

    if is_open_url(target):
        return {
            "version": 1,
            "action": "open_url",
            "url": target,
        }

    resolved = resolve_path_candidate(target, cwd)
    if resolved is None:
        return None

    path, target_type, line, column = resolved
    request: dict[str, object] = {
        "version": 1,
        "action": "open_vscode_remote",
        "path": path,
        "target_type": target_type,
    }
    if target_type == "file":
        request["workspace_path"] = str(Path(os.path.expanduser(cwd)).resolve(strict=False))
    if ssh_host:
        request["ssh_host"] = ssh_host
    if line is not None:
        request["line"] = line
    if column is not None:
        request["column"] = column
    return request


def send_request(socket_path: str, request: dict[str, object], timeout: float) -> dict[str, object]:
    payload = json.dumps(request, separators=(",", ":")).encode("utf-8") + b"\n"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(socket_path)
        client.sendall(payload)
        raw_response = client.recv(65536)

    if not raw_response:
        return {"ok": True}
    return json.loads(raw_response.decode("utf-8"))


def bridge_available(socket_path: str, timeout: float) -> bool:
    try:
        response = send_request(socket_path, {"version": 1, "action": "ping"}, timeout)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    return bool(response.get("ok", False))


def osc8(uri: str, label: str) -> str:
    return f"\033]8;;{uri}\033\\{label}\033]8;;\033\\"


def vscode_url(request: dict[str, object]) -> str:
    if "ssh_host" not in request:
        raise KeyError("ssh_host")
    host = urllib.parse.quote(str(request["ssh_host"]), safe="@.-_:")
    path = urllib.parse.quote(str(request["path"]), safe="/:._-")
    return f"vscode://vscode-remote/ssh-remote+{host}{path}"


def fallback_message(request: dict[str, object] | None, message: str, mode: str) -> int:
    if mode == "none":
        return 1

    if mode == "auto":
        mode = "message" if os.environ.get("TMUX") else "osc8"

    if mode == "message":
        subprocess.run(["tmux", "display-message", f"tmux-opener: {message}"], check=False)
        return 1

    if request and request.get("action") == "open_url":
        uri = str(request["url"])
        print(osc8(uri, f"Open URL: {uri}"))
        return 1

    if request and request.get("action") == "open_vscode_remote":
        try:
            uri = vscode_url(request)
        except KeyError:
            print(f"tmux-opener: {message}; no SSH host available for OSC 8 fallback", file=sys.stderr)
            return 1
        print(osc8(uri, f"Open in VS Code: {request['path']}"))
        return 1

    if request and request.get("action") == "open_remote_localhost":
        print(f"tmux-opener: {message}; remote localhost forwarding requires the bridge", file=sys.stderr)
        return 1

    print(f"tmux-opener: {message}", file=sys.stderr)
    return 1


def deliver_request(
    socket_path: str,
    request: dict[str, object],
    timeout: float,
    log_path: str | None,
    fallback: str,
) -> int:
    try:
        response = send_request(socket_path, request, timeout)
    except OSError as exc:
        log_line(log_path, f"send failed: socket={socket_path} {describe_request(request)} error={exc}")
        return fallback_message(request, f"bridge unavailable at {socket_path}: {exc}", fallback)
    except json.JSONDecodeError as exc:
        log_line(log_path, f"send failed: socket={socket_path} {describe_request(request)} error=invalid response: {exc}")
        return fallback_message(request, f"invalid bridge response: {exc}", fallback)

    if not response.get("ok", False):
        error = response.get("error", "request rejected")
        log_line(log_path, f"send rejected: socket={socket_path} {describe_request(request)} error={error}")
        return fallback_message(request, str(error), fallback)

    log_line(log_path, f"send ok: socket={socket_path} {describe_request(request)}")
    return 0
