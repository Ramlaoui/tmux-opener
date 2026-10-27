---
title: Opener rules
description: Choose per file pattern whether a remote file opens in VS Code, inline, as a local preview or as a download.
---

# Opener rules

By default <kbd>o</kbd> opens remote files in VS Code. Opener rules change that per file pattern. They live on your laptop in `~/.config/tmux-opener/settings.json` (or `$XDG_CONFIG_HOME/tmux-opener/settings.json`) and apply to every client right away, without a restart.

Edit them on the **Openers** page of `tmux-opener dashboard`, or with <kbd>Tab</kbd> in either tmux dashboard: <kbd>←</kbd>/<kbd>→</kbd> change the selected value, <kbd>a</kbd> adds a rule, <kbd>x</kbd> deletes it and <kbd>J</kbd>/<kbd>K</kbd> reorder.

## Openers

| Opener | Effect |
| --- | --- |
| `vscode` | VS Code Remote-SSH at the selected line (default) |
| `tmux` | Show the file in the [inline view](inline-view.md) on the host, shown as **Inline** |
| `preview` | Copy into `~/.cache/tmux-opener/preview/` and open it locally; PDFs use the PDF viewer below |
| `download` | Queue a normal [download](downloads.md) into Downloads |

The first matching rule wins. Folders always open in VS Code.

## Example

```json
{
  "rules": [
    {"pattern": "*.log", "opener": "tmux"},
    {"pattern": "*.pdf", "opener": "preview"},
    {"pattern": "*/figures/*.png", "opener": "preview"},
    {"pattern": "*.ckpt", "opener": "download"}
  ],
  "vscode_file_window": "new",
  "vscode_folder_window": "new",
  "pdf_viewer": "auto",
  "download_notifications": "all"
}
```

Patterns are case-insensitive shell globs. A pattern without `/` matches the file name; otherwise it matches the full remote path.

## Other settings

| Setting | Values |
| --- | --- |
| `vscode_file_window`, `vscode_folder_window` | `new` or `reuse` |
| `pdf_viewer` | `auto`, `zathura`, `skim`, `sioyek`, `acrobat` or `system`; the dashboards offer the installed ones |
| `download_notifications` | `all`, `failures` or `off`; local previews are never announced |

Sioyek refreshes without taking focus. Acrobat on macOS reopens the matching PDF at the same page and zoom, and refuses to refresh unsaved edits. The flags `--vscode-file-window`, `--vscode-folder-window` and `--pdf-viewer`, and `TMUX_OPENER_PDF_VIEWER`, override the file.

## Why there are no custom commands

Settings never contain commands, because a forwarded remote session can edit them. For the same reason `preview` only accepts documents, images, audio and video (`.pdf`, `.md`, `.txt`, `.csv`, `.png`, `.mp4`, …). Formats that can run code when opened, such as `.html`, `.svg`, `.command` or office files, are refused; use `download` for those.
