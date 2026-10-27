---
title: Uploads
description: Pick files on your laptop and upload them into the tmux pane's directory on the host.
---

# Uploads

Press <kbd>prefix</kbd> <kbd>P</kbd> in a pane on the host. A file dialog opens **on your laptop**, and the files you pick are copied into that pane's current directory. Pick several files to upload them together.

## Safe by construction

- **The host only names the destination.** It cannot choose, list or read files on your laptop. Nothing is sent unless you pick it, in a dialog that shows the host and directory it uploads to.
- **No overwrites.** A name that already exists gets ` (1)`, ` (2)` and so on.
- **Atomic.** Each file is written to a hidden temporary file in the directory and renamed only once every byte has arrived, so a failed or cancelled upload leaves nothing behind.

Uploads share the download queue, dashboards and notifications. Retrying a failed upload sends the files that did not arrive, without asking again. On macOS the picker is the native open dialog; on Linux it is `zenity` or `kdialog`, with Python Tk as a fallback. Folders are not supported yet.

!!! note "Why not drag and drop?"

    Dropping a file on a terminal only pastes its local path. Uploading it would mean letting the host ask for local paths, which the [trust model](../reference/security.md) rules out.

Change the key with:

```tmux
set -g @tmux_opener_upload_key 'P'
```

The default is <kbd>P</kbd> because TPM already uses <kbd>prefix</kbd> <kbd>U</kbd> to update plugins.
