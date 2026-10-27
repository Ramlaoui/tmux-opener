---
title: tmux-opener
description: Select a URL, a path or a file in tmux on an SSH host, press a key, and it opens on your laptop.
hide:
  - navigation
  - toc
---

# tmux-opener

When you work over SSH, the links, tracebacks and files in your terminal are stuck on the server. You copy URLs by hand, hunt for the file in your editor, and `scp` results back.

tmux-opener sends them to your laptop. Select one in tmux and press a key: it opens in your browser, in VS Code at the right line, or lands in your Downloads folder.

<video class="demo hero" autoplay loop muted playsinline preload="metadata" poster="assets/media/hero.webp" aria-label="Pressing o on a URL opens the laptop's browser; on a traceback line it opens VS Code at that line"><source src="assets/media/hero.mp4" type="video/mp4"></video>

```sh
tmux-opener ssh devbox
```

[Install](getting-started/installation.md){ .md-button .md-button--primary } [GitHub](https://github.com/Ramlaoui/tmux-opener){ .md-button }

<div class="demos" markdown>

<div markdown>

### Open URLs

Select a link in copy mode and press <kbd>o</kbd>. It opens in your laptop's browser.

<video class="demo" autoplay loop muted playsinline preload="metadata" poster="assets/media/open-url.webp" aria-label="A URL selected in tmux opens in the laptop's browser"><source src="assets/media/open-url.mp4" type="video/mp4"></video>

</div>

<div markdown>

### Preview in the terminal

<kbd>i</kbd> shows images, GIFs, PDFs, tables and folders without leaving tmux.

<video class="demo" autoplay loop muted playsinline preload="metadata" poster="assets/media/inline-view.webp" aria-label="Inline view plays a GIF, then shows a PDF and a folder in the terminal"><source src="assets/media/inline-view.mp4" type="video/mp4"></video>

</div>

<div markdown>

### Open files in VS Code

Press <kbd>o</kbd> on `path:line` from a traceback. VS Code opens it over Remote-SSH at that line.

<video class="demo" autoplay loop muted playsinline preload="metadata" poster="assets/media/open-vscode.webp" aria-label="A traceback path opens VS Code Remote-SSH at the failing line"><source src="assets/media/open-vscode.mp4" type="video/mp4"></video>

</div>

<div markdown>

### Open remote localhost

`localhost:8888` on the host opens through a private SSH tunnel.

<video class="demo" autoplay loop muted playsinline preload="metadata" poster="assets/media/localhost.webp" aria-label="A localhost URL on the host opens through an SSH tunnel"><source src="assets/media/localhost.mp4" type="video/mp4"></video>

</div>

<div markdown>

### Pick from the screen

<kbd>prefix</kbd> <kbd>o</kbd> lists every URL and path in the pane. No copy mode needed.

<video class="demo" autoplay loop muted playsinline preload="metadata" poster="assets/media/picker.webp" aria-label="The fzf target picker lists URLs and paths from the pane"><source src="assets/media/picker.mp4" type="video/mp4"></video>

</div>

<div markdown>

### Download

<kbd>d</kbd> copies files, folders or globs to your Downloads folder.

<video class="demo" autoplay loop muted playsinline preload="metadata" poster="assets/media/download.webp" aria-label="Pressing d downloads the selected files to the laptop with a notification"><source src="assets/media/download.mp4" type="video/mp4"></video>

</div>

<div markdown>

### Save as, or upload

<kbd>D</kbd> asks where to save on your laptop. <kbd>prefix</kbd> <kbd>P</kbd> uploads files into the pane's directory.

<video class="demo" autoplay loop muted playsinline preload="metadata" poster="assets/media/save-as.webp" aria-label="Pressing D opens a native save dialog on the laptop"><source src="assets/media/save-as.mp4" type="video/mp4"></video>

</div>

<div markdown>

### Dashboard

<kbd>prefix</kbd> <kbd>O</kbd> shows transfers, clients and opener rules. `tmux-opener dashboard` opens the same views in a browser.

<video class="demo" autoplay loop muted playsinline preload="metadata" poster="assets/media/dashboard.webp" aria-label="The tmux dashboard shows transfers, clients and opener rules"><source src="assets/media/dashboard.mp4" type="video/mp4"></video>

</div>

</div>

## How it works

A tmux plugin on the host sends small JSON requests over a Unix socket forwarded by SSH. A client on your laptop checks each one and opens it. The host never sends commands. [Security model](reference/security.md)

## Install

=== "On the host"

    ```tmux
    set -g @plugin 'Ramlaoui/tmux-opener'
    ```

    Then press <kbd>prefix</kbd> <kbd>I</kbd>.

=== "On your laptop"

    ```sh
    tar -xzf tmux-opener-client-vX.Y.Z.tar.gz -C ~/.local/share
    ln -sf ~/.local/share/tmux-opener-client/bin/tmux-opener ~/.local/bin/
    ln -sf ~/.local/share/tmux-opener-client/bin/tmux-opener-client ~/.local/bin/
    tmux-opener ssh HOST
    ```

    Download the archive from the [latest release](https://github.com/Ramlaoui/tmux-opener/releases).

[Full installation guide](getting-started/installation.md)
