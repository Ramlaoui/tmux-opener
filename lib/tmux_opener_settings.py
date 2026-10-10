"""Desktop opener settings shared by every local client and dashboard.

Settings select among fixed, client-owned behaviours.  They never contain
commands, so a forwarded remote session that edits them cannot make the
desktop run arbitrary programs.
"""

from __future__ import annotations

import fnmatch
import json
import os
import platform
import shutil
import tempfile
from pathlib import Path


# "tmux" asks the remote plugin to show the file in a tmux popup itself.
OPENERS = ("vscode", "tmux", "preview", "download")
WINDOW_POLICIES = ("new", "reuse")
PDF_VIEWERS = ("auto", "zathura", "skim", "sioyek", "acrobat", "system")
PDF_APPLICATIONS = {
    "skim": ("Skim.app",),
    "sioyek": ("sioyek.app", "Sioyek.app"),
    "acrobat": ("Adobe Acrobat DC/Adobe Acrobat.app", "Adobe Acrobat.app"),
}
MAX_RULES = 64
# Local previews hand a copied file to the desktop's default application.
# Formats that can execute code when opened (scripts, .command, HTML, SVG,
# office macros) are deliberately absent.
PREVIEW_SUFFIXES = frozenset({
    ".pdf", ".txt", ".md", ".log", ".csv", ".tsv", ".json",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic",
    ".mp4", ".mov", ".mkv", ".webm", ".avi", ".mp3", ".wav", ".flac", ".ogg", ".m4a",
})
DEFAULTS: dict[str, object] = {
    "rules": [],
    "vscode_folder_window": "new",
    "vscode_file_window": "new",
    "pdf_viewer": "auto",
}


def pdf_application(viewer: str) -> Path | None:
    if platform.system() != "Darwin":
        return None
    for root in (Path("/Applications"), Path.home() / "Applications"):
        for name in PDF_APPLICATIONS.get(viewer, ()):
            application = root / name
            if application.is_dir():
                return application
    return None


def sioyek_executable() -> str | None:
    executable = shutil.which("sioyek")
    if executable:
        return executable
    application = pdf_application("sioyek")
    bundled = application / "Contents/MacOS/sioyek" if application else None
    return str(bundled) if bundled and os.access(bundled, os.X_OK) else None


def available_pdf_viewers() -> list[str]:
    return [viewer for viewer in PDF_VIEWERS if (
        viewer in {"auto", "system"}
        or (viewer == "zathura" and shutil.which("zathura"))
        or (viewer == "sioyek" and sioyek_executable())
        or pdf_application(viewer)
    )]


def settings_path() -> Path:
    config = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(config) / "tmux-opener" / "settings.json"


def validate(raw: object) -> dict[str, object]:
    """Return complete settings, raising ValueError on any invalid field."""

    if not isinstance(raw, dict):
        raise ValueError("settings must be an object")
    unknown = set(raw) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown setting: {sorted(unknown)[0]}")
    settings = {**DEFAULTS, **raw}
    for key, choices in (("vscode_folder_window", WINDOW_POLICIES), ("vscode_file_window", WINDOW_POLICIES),
                         ("pdf_viewer", PDF_VIEWERS)):
        if settings[key] not in choices:
            raise ValueError(f"{key} must be one of: {', '.join(choices)}")
    rules = settings["rules"]
    if not isinstance(rules, list) or len(rules) > MAX_RULES:
        raise ValueError(f"rules must be a list of at most {MAX_RULES} rules")
    clean = []
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {"pattern", "opener"}:
            raise ValueError("each rule needs exactly a pattern and an opener")
        pattern, opener = rule["pattern"], rule["opener"]
        if not isinstance(pattern, str) or not pattern.strip() or len(pattern) > 256 or any(c in pattern for c in "\x00\r\n"):
            raise ValueError("rule patterns must be non-empty single-line text")
        if opener not in OPENERS:
            raise ValueError(f"rule opener must be one of: {', '.join(OPENERS)}")
        clean.append({"pattern": pattern.strip(), "opener": opener})
    settings["rules"] = clean
    return settings


def load(path: Path | None = None) -> tuple[dict[str, object], str | None]:
    """Return settings and a load error; a broken file falls back to defaults."""

    path = path or settings_path()
    try:
        return validate(json.loads(path.read_text(encoding="utf-8"))), None
    except FileNotFoundError:
        return dict(DEFAULTS), None
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        return dict(DEFAULTS), f"ignoring {path}: {exc}"


def save(raw: object, path: Path | None = None) -> dict[str, object]:
    settings = validate(raw)
    path = path or settings_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".settings-", delete=False) as handle:
        json.dump(settings, handle, indent=2)
        handle.write("\n")
    os.replace(handle.name, path)
    return settings


def opener_for(settings: dict[str, object], path: str) -> str:
    """Return the first matching rule's opener for a remote file path.

    Patterns without a slash match the file name; others match the full path.
    Matching ignores case so ``*.pdf`` also covers ``REPORT.PDF``.
    """

    name = path.rstrip("/").rsplit("/", 1)[-1].lower()
    for rule in settings["rules"]:  # type: ignore[union-attr]
        pattern = rule["pattern"].lower()
        if fnmatch.fnmatchcase(path.lower() if "/" in pattern else name, pattern):
            return rule["opener"]
    return "vscode"
