---
title: Inline view
description: Preview files, images, PDFs, tables and folders in a tmux popup on the host.
---

# Inline view

Select a path in copy mode and press <kbd>i</kbd> to view it on the host in a large tmux popup. Nothing crosses the bridge and nothing opens on your laptop; <kbd>q</kbd> closes the view.

<video class="demo" autoplay loop muted playsinline preload="metadata" poster="../../assets/media/inline-view.webp" aria-label="Inline view plays a GIF, then shows a PDF and a folder in the terminal"><source src="../assets/media/inline-view.mp4" type="video/mp4"></video>

The viewer picks the best tool the host has:

| File | Viewer |
| --- | --- |
| text and code | `bat` (or `batcat`) with the selected line highlighted, otherwise `less` |
| `.csv`, `.tsv` | Aligned columns with a pinned header, up to 5000 rows |
| `.md` | `glow` when installed, otherwise a built-in renderer |
| `.json` | `jq`, otherwise Python's `json.tool` |
| images | `chafa` or `timg`; real pixels in Ghostty or kitty |
| `.gif` | Animated in Ghostty or kitty when the host has `ffmpeg` |
| `.pdf` | Pages in real pixels with `pdftoppm` and `chafa` in Ghostty or kitty, otherwise `pdftotext` |
| binary | File type and size instead of raw bytes |
| folders | A file browser with a preview pane |

`path:LINE` opens text at that line. Files over 20 MiB skip highlighting and stream through `less`.

## Images and PDFs in pixels

In Ghostty and kitty, `chafa` draws images with the terminal's graphics protocol. tmux keeps graphics out of popups, so image and PDF views open in a tmux window instead. GIFs play and loop when `ffmpeg` and `ffprobe` are installed, one frame at a time, so a slow link lowers the frame rate instead of the view lagging. In a PDF, <kbd>space</kbd>/<kbd>b</kbd> or the arrows change page, <kbd>g</kbd>/<kbd>G</kbd> jump to the first or last page, and `report.pdf:3` opens page 3.

## Tables

CSV and TSV files open as aligned columns with the header pinned while you scroll. Use <kbd>j</kbd>/<kbd>k</kbd>, <kbd>space</kbd>/<kbd>b</kbd>, <kbd>h</kbd>/<kbd>l</kbd>, <kbd>g</kbd>/<kbd>G</kbd> and <kbd>/</kbd> to search.

## Folders

Selecting a folder opens a browser with a preview pane in wide panes:

| Key | Action |
| --- | --- |
| <kbd>j</kbd>/<kbd>k</kbd>, arrows | Move |
| <kbd>Enter</kbd> | Open a folder or preview a file |
| <kbd>h</kbd>, <kbd>←</kbd>, `../` | Go up |
| <kbd>space</kbd> | Mark files and folders, across folders |
| <kbd>a</kbd> | Mark everything |
| <kbd>d</kbd> / <kbd>D</kbd> | [Download](downloads.md) the marked entries, or the one under the cursor |
| <kbd>/</kbd> | Search names |
| <kbd>.</kbd> | Show hidden files |

## Make it the default for some files

The `tmux` [opener rule](opener-rules.md), shown as **Inline**, makes <kbd>o</kbd> use this viewer for matching files, for example every `*.log`. The desktop only answers "show it inline" and the host displays its own file.
