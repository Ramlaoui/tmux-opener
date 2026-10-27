---
title: "tmux-opener: remote tmux, wired to your laptop"
description: Select a URL, a traceback or a file in tmux on any SSH host and press one key. It opens in your laptop's browser or VS Code, lands in your Downloads folder, or previews right in the terminal.
hide:
  - navigation
  - toc
---

<div class="to-hero" markdown>

<span class="to-eyebrow">tmux plugin · desktop client · SSH bridge</span>

# Press a key in remote tmux. It opens *on your laptop.*

<p class="to-tagline">Select a URL, a traceback or a file in tmux on any SSH host and press <kbd>o</kbd>. tmux-opener opens it in your laptop's browser or in VS Code at the right line, tunnels <code>localhost</code> links, downloads files to your Downloads folder, and previews images and PDFs right in the terminal.</p>

[Get started](getting-started/installation.md){ .md-button .md-button--primary }
[See it in action](#take-the-tour){ .md-button }
[GitHub](https://github.com/Ramlaoui/tmux-opener){ .md-button }

<div class="to-install"><b>$</b> tmux-opener ssh <b>devbox</b></div>

</div>

<div class="to-points">
<span>Any host you can SSH into</span>
<span>Plain tmux plugin, no daemon on the host</span>
<span>Structured requests, never remote commands</span>
<span>Python standard library only</span>
</div>

<div class="to-window">
<div class="to-bar"><i></i><i></i><i></i><span>demo@devbox: ~/vision-lab</span></div>
<video autoplay loop muted playsinline preload="metadata" poster="assets/media/hero.webp" aria-label="Pressing o on a URL in remote tmux opens the laptop's browser, and on a traceback line opens VS Code at that line"><source src="assets/media/hero.mp4" type="video/mp4"></video>
</div>
<p class="to-caption">Copy mode on <code>devbox</code>: press <kbd>o</kbd> on a link and it opens in the laptop's browser; press <kbd>o</kbd> on a traceback line and VS Code opens at that line.</p>

## The terminal is remote. Your tools are not.

You train models on a cluster, tail logs on a server, and debug in a container. Every link, path and figure on that screen belongs on your laptop: a browser tab, a VS Code window at the failing line, a PDF viewer, your Downloads folder. Usually that means copying text by hand, rebuilding URLs and juggling `scp` commands.

tmux-opener connects remote tmux to your desktop over the SSH connection you already use. Select something and press a key: the request crosses the bridge and your laptop handles it.

<div class="grid cards" markdown>

-   :material-web:{ .lg .middle } __URLs in your browser__

    ---

    Docs, dashboards and pull requests printed on the host open as tabs on your laptop.

-   :material-microsoft-visual-studio-code:{ .lg .middle } __Tracebacks in VS Code__

    ---

    `src/model.py:42` opens through Remote-SSH at that line, in a window rooted at the pane's directory.

-   :material-lan-connect:{ .lg .middle } __localhost, tunnelled__

    ---

    `http://localhost:8888` on the host becomes a private SSH tunnel and opens locally. Notebooks and TensorBoard just work.

-   :material-magnify:{ .lg .middle } __Pick from the screen__

    ---

    <kbd>prefix</kbd> <kbd>o</kbd> lists every URL and path visible in the pane in `fzf`, so you don't need copy mode.

-   :material-image-filter-hdr:{ .lg .middle } __Preview in the terminal__

    ---

    <kbd>i</kbd> shows images and PDF pages in real pixels in Ghostty or kitty, plus CSV tables, Markdown, JSON and a folder browser.

-   :material-tray-arrow-down:{ .lg .middle } __Download in one key__

    ---

    <kbd>d</kbd> sends files, folders or globs to your Downloads folder, resumably. <kbd>D</kbd> asks where to save.

-   :material-tray-arrow-up:{ .lg .middle } __Upload into the pane__

    ---

    <kbd>prefix</kbd> <kbd>P</kbd> opens a file picker on your laptop and copies what you pick into the pane's directory.

-   :material-monitor-dashboard:{ .lg .middle } __Dashboards on both sides__

    ---

    Follow transfers, restart clients, add bridges and choose openers from a tmux popup or a browser page.

</div>

## Take the tour

<div class="to-tour" markdown>
<div markdown>

### Open URLs on your laptop

Select a link in copy mode and press <kbd>o</kbd>. The host sends an *Open Request* through the forwarded socket and your laptop opens it in the default browser. tmux briefly shows which route it took.

<span class="to-keys">copy mode → select → o</span>

[Opening URLs and files](guides/open.md)

</div>
<div class="to-window">
<div class="to-bar"><i></i><i></i><i></i><span>browser</span></div>
<video autoplay loop muted playsinline preload="metadata" poster="assets/media/open-url.webp" aria-label="A URL selected in tmux opens in the laptop's browser"><source src="assets/media/open-url.mp4" type="video/mp4"></video>
</div>
</div>

<div class="to-tour" markdown>
<div markdown>

### Jump from a traceback to the line

A path such as `src/vision/model.py:24` opens in VS Code through Remote-SSH, at line 24, in a window rooted at the pane's working directory. Relative paths resolve against the pane, not your laptop.

<span class="to-keys">copy mode → select path:line → o</span>

[Opening URLs and files](guides/open.md#files-and-folders-in-vs-code)

</div>
<div class="to-window">
<div class="to-bar"><i></i><i></i><i></i><span>VS Code · SSH: devbox</span></div>
<video autoplay loop muted playsinline preload="metadata" poster="assets/media/open-vscode.webp" aria-label="A traceback path opens VS Code Remote-SSH at the failing line"><source src="assets/media/open-vscode.mp4" type="video/mp4"></video>
</div>
</div>

<div class="to-tour" markdown>
<div markdown>

### Remote localhost, opened locally

`localhost:8888` means the host, not your laptop. The client starts a private SSH tunnel with every inherited forward disabled, checks that the local port listens, then opens the rewritten URL.

<span class="to-keys">select localhost:8888 → o → http://127.0.0.1:18888</span>

[localhost tunnels](guides/open.md#remote-localhost-urls)

</div>
<div class="to-window">
<div class="to-bar"><i></i><i></i><i></i><span>browser · 127.0.0.1:18888</span></div>
<video autoplay loop muted playsinline preload="metadata" poster="assets/media/localhost.webp" aria-label="A localhost URL on the host opens through an SSH tunnel"><source src="assets/media/localhost.mp4" type="video/mp4"></video>
</div>
</div>

<div class="to-tour" markdown>
<div markdown>

### Pick any target on screen

<kbd>prefix</kbd> <kbd>o</kbd> lists the URLs and paths visible in the pane in `fzf` and opens the one you choose.

<span class="to-keys">prefix o → type to filter → enter</span>

[The target picker](guides/picker.md)

</div>
<div class="to-window">
<div class="to-bar"><i></i><i></i><i></i><span>demo@devbox: ~/vision-lab</span></div>
<video autoplay loop muted playsinline preload="metadata" poster="assets/media/picker.webp" aria-label="The fzf target picker lists URLs and paths from the pane"><source src="assets/media/picker.mp4" type="video/mp4"></video>
</div>
</div>

<div class="to-tour" markdown>
<div markdown>

### See it without leaving tmux

<kbd>i</kbd> previews the selection on the host. In Ghostty and kitty, images and PDF pages are drawn in real pixels, and folders open in a browser with a preview pane and multi-select downloads.

<span class="to-keys">copy mode → select → i</span>

[Inline view](guides/inline-view.md)

</div>
<div class="to-window">
<div class="to-bar"><i></i><i></i><i></i><span>demo@devbox: inline view</span></div>
<video autoplay loop muted playsinline preload="metadata" poster="assets/media/inline-view.webp" aria-label="Inline view shows a figure and a PDF in the terminal"><source src="assets/media/inline-view.mp4" type="video/mp4"></video>
</div>
</div>

<div class="to-tour" markdown>
<div markdown>

### Files to your laptop, and back

<kbd>d</kbd> downloads files, folders or a glob such as `runs/*/loss_epoch050.png` to your Downloads folder, and resumes if the connection drops. A notification says when it's done. <kbd>prefix</kbd> <kbd>P</kbd> goes the other way.

<span class="to-keys">select → d · D to choose where · prefix P to upload</span>

[Downloads](guides/downloads.md) · [Uploads](guides/uploads.md)

</div>
<div class="to-window">
<div class="to-bar"><i></i><i></i><i></i><span>demo@devbox → demo-mac</span></div>
<video autoplay loop muted playsinline preload="metadata" poster="assets/media/download.webp" aria-label="Pressing d downloads the selected files to the laptop with a notification"><source src="assets/media/download.mp4" type="video/mp4"></video>
</div>
</div>

<div class="to-tour" markdown>
<div markdown>

### Everything in one dashboard

<kbd>prefix</kbd> <kbd>O</kbd> opens a live dashboard on the host: transfers with progress, cancel and retry, the desktop clients, and opener rules. `tmux-opener dashboard` opens the same views in your browser.

<span class="to-keys">prefix O → Tab between Transfers, Clients, Openers</span>

[Dashboards](guides/dashboards.md)

</div>
<div class="to-window">
<div class="to-bar"><i></i><i></i><i></i><span>demo@devbox: dashboard</span></div>
<video autoplay loop muted playsinline preload="metadata" poster="assets/media/dashboard.webp" aria-label="The tmux dashboard shows transfers, clients and opener rules"><source src="assets/media/dashboard.mp4" type="video/mp4"></video>
</div>
</div>

## How it works

<div class="to-flow" markdown>
<div markdown>

#### On the SSH host

- the **Remote Opener Plugin**, a tmux plugin
- turns the selection into a JSON request
- falls back to the host's own opener when no bridge answers

</div>
<div class="to-wire"><b>→</b>SSH RemoteForward<br>Unix socket</div>
<div markdown>

#### On your laptop

- the **Local Opener Client**
- checks each request against an allowlist
- opens the browser or VS Code, runs transfers and shows dialogs

</div>
</div>

`tmux-opener ssh HOST` writes a small managed SSH config snippet that forwards a Unix socket from the host back to the client, starts the client, and connects. After that a plain `ssh HOST` carries the bridge too. The host never sends shell commands: it sends data such as *open this URL* or *download this path*, and the client decides what to run. [Read the security model](reference/security.md).

## Install in a minute

=== "On the SSH host"

    Add the plugin with [TPM](https://github.com/tmux-plugins/tpm), then press <kbd>prefix</kbd> <kbd>I</kbd>:

    ```tmux
    set -g @plugin 'Ramlaoui/tmux-opener'
    ```

=== "On your laptop"

    Unpack the client from the [latest release](https://github.com/Ramlaoui/tmux-opener/releases) and connect:

    ```sh
    tar -xzf tmux-opener-client-vX.Y.Z.tar.gz -C ~/.local/share
    ln -sf ~/.local/share/tmux-opener-client/bin/tmux-opener ~/.local/bin/
    ln -sf ~/.local/share/tmux-opener-client/bin/tmux-opener-client ~/.local/bin/
    tmux-opener ssh HOST
    ```

[Full installation guide](getting-started/installation.md){ .md-button .md-button--primary }
[Quickstart](getting-started/quickstart.md){ .md-button }
