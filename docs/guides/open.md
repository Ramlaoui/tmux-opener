---
title: Opening URLs and files
description: Open URLs in your laptop's browser, remote files in VS Code at the right line, and remote localhost services through SSH tunnels.
---

# Opening URLs and files

In tmux copy mode on the host, select text and press <kbd>o</kbd>. What happens depends on what you selected.

| Selection | Opens on your laptop |
| --- | --- |
| `https://…` or `http://…` | Your default browser |
| `http://localhost:8888/…`, `127.0.0.1:6006` | A private SSH tunnel, then the browser |
| `path/to/file.py:42:7` | VS Code Remote-SSH at line 42, column 7 |
| `path/to/folder` | A VS Code Remote-SSH window for the folder |

tmux briefly shows the route it used, for example *opened via local opener bridge*.

## URLs in your browser

<div class="to-window">
<div class="to-bar"><i></i><i></i><i></i><span>browser</span></div>
<video autoplay loop muted playsinline preload="metadata" poster="../../assets/media/open-url.webp" aria-label="A URL selected in tmux opens in the laptop's browser"><source src="../assets/media/open-url.mp4" type="video/mp4"></video>
</div>

By default the client accepts only `http` and `https` URLs, so a remote session cannot launch arbitrary local URL handlers. Start the client with `--allow-url-scheme SCHEME` to allow another scheme.

## Files and folders in VS Code

<div class="to-window">
<div class="to-bar"><i></i><i></i><i></i><span>VS Code · SSH: devbox</span></div>
<video autoplay loop muted playsinline preload="metadata" poster="../../assets/media/open-vscode.webp" aria-label="A traceback path opens VS Code Remote-SSH at the failing line"><source src="../assets/media/open-vscode.mp4" type="video/mp4"></video>
</div>

Select a path from a traceback, a compiler error or `grep -n` output. tmux-opener understands `path`, `path:line` and `path:line:column`, and resolves relative paths against the pane's working directory on the host.

Files open in a new VS Code Remote-SSH window rooted at the pane's directory, so the editor has the project around it. Folders open in their own window. To reuse an existing window instead, set the window policy to `reuse` on the [Openers page](opener-rules.md).

VS Code needs the `code` CLI and the Remote-SSH extension on your laptop. Without `code`, the client opens a `vscode://` link instead.

!!! info "Not every file belongs in VS Code"

    [Opener rules](opener-rules.md) can send `*.log` to the inline viewer, `*.pdf` to a local preview or `*.ckpt` straight to Downloads.

## Remote localhost URLs

<div class="to-window">
<div class="to-bar"><i></i><i></i><i></i><span>browser · 127.0.0.1:18888</span></div>
<video autoplay loop muted playsinline preload="metadata" poster="../../assets/media/localhost.webp" aria-label="A localhost URL on the host opens through an SSH tunnel"><source src="../assets/media/localhost.mp4" type="video/mp4"></video>
</div>

`localhost` printed on the host means the host. When you open `http://localhost:8888/?token=…`, `127.0.0.1:6006` or `localhost:8080`, the client:

1. starts a supervised auxiliary SSH connection to the host using your SSH config, with **every inherited forward disabled**,
2. adds only the forward it needs, for example `127.0.0.1:18888 → localhost:8888`,
3. checks that the local port is listening,
4. opens the rewritten URL, keeping the path, query and fragment.

Local ports come from `18000`–`18999`, preferring `10000 + remote port`. The tunnel is reused for later opens and closed when the client stops. It never requests the bridge's own `RemoteForward`, and host aliases, `ProxyJump`, identities and host-key checks still come from your SSH config.

You can also send a target from a script on the host:

```sh
tmux-opener-send localhost:8080
tmux-opener-send http://127.0.0.1:8888/lab?token=abc
```

## When there is no bridge

The copy-mode key does not guess whether the pane is an SSH session. It pings the forwarded socket: if the client answers, the request crosses the bridge; otherwise tmux-opener falls back to the host's own opener (`open` or `xdg-open`). This makes the same keys work in local tmux.

Choose the behaviour with `@tmux_opener_fallback`:

| Value | Without a bridge |
| --- | --- |
| `auto` (default) | `command` if `@tmux_opener_fallback_command` is set, otherwise `local` |
| `local` | Open with the host's `open` or `xdg-open` |
| `command` | Run `@tmux_opener_fallback_command` with the selection |
| `none` | Show an error |

Downloads and uploads always need the bridge.
