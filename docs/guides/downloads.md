---
title: Downloads
description: Download remote files, folders and globs to your laptop with one key, with resumable transfers and notifications.
---

# Downloads

Select one or more paths in copy mode and press:

- <kbd>d</kbd> to download into your laptop's **Downloads** folder (Linux honours the XDG Downloads setting),
- <kbd>D</kbd> to choose the destination in a **save dialog on your laptop**.

<video class="demo" autoplay loop muted playsinline preload="metadata" poster="../../assets/media/download.webp" aria-label="Pressing d downloads the selected files to the laptop with a notification"><source src="../assets/media/download.mp4" type="video/mp4"></video>

tmux confirms that the transfer was queued. Your laptop shows a notification when it finishes or fails (Notification Center on macOS, `notify-send` on Linux).

## What you can select

- **Several paths**, one per line or separated by spaces. Quote paths that contain spaces.
- **Relative paths**, resolved against the pane's working directory, and `path:line:column` references.
- **Folders**, downloaded whole into `Downloads/NAME/`.
- **Globs** such as `runs/exp-42/*.png` or `runs/**/metrics.csv`. The host expands them and the client downloads up to 1000 matches into a folder named after the part before the first wildcard (`Downloads/exp-42/`), keeping subpaths.

URLs are rejected: open them instead.

## Choose where to save

<video class="demo" autoplay loop muted playsinline preload="metadata" poster="../../assets/media/save-as.webp" aria-label="Pressing D opens a native save dialog on the laptop"><source src="../assets/media/save-as.mp4" type="video/mp4"></video>

<kbd>D</kbd> opens the native save dialog on macOS, and `zenity`, `kdialog` or Python Tk on Linux and Windows. It asks once per file. Cancelling a dialog skips that file. Existing files are never overwritten: choose a new name.

## Transfers you can trust

- **Resumable.** Received bytes are kept in a private partial copy under `~/.cache/tmux-opener/partial`. A dropped connection (retried automatically twice), a cancel, a client restart or a manual retry continues where it stopped, as long as the remote file's size and modification time are unchanged. Unused partial copies are deleted after 7 days.
- **Atomic.** Files appear at their destination only after the transfer succeeds.
- **No overwrites.** <kbd>d</kbd> adds ` (1)`, ` (2)` and so on when a name exists.
- **Fast when it can be.** The client uses `rsync` when both machines have rsync 3; otherwise it streams `tar` over SSH and extracts it safely, refusing entries that escape the folder and skipping links that leave it and device files.

Transfers run in the background over SSH with the same host alias as the bridge. They need key or agent authentication, since they cannot prompt for a password. They honour your SSH config and disable inherited forwards and shared connections.

## Follow, cancel and retry

Two transfers run at once and the rest wait in a queue. Open the [dashboard](dashboards.md) with <kbd>prefix</kbd> <kbd>O</kbd> to see progress, <kbd>c</kbd> to cancel and <kbd>r</kbd> to retry. From your laptop:

```sh
tmux-opener downloads devbox
tmux-opener downloads --json
```

Choose which notifications to get (all, failures only, or off) on the [Openers page](opener-rules.md).
