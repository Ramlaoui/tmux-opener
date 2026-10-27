---
title: Installation
description: Install the tmux plugin on your SSH hosts and the desktop client on your laptop.
---

# Installation

tmux-opener has two parts. Install each where it runs:

| Part | Where | What it does |
| --- | --- | --- |
| **Remote Opener Plugin** | every SSH host where you run tmux | Adds the keys and turns selections into requests |
| **Local Opener Client** | your laptop or desktop | Receives requests and opens, downloads or uploads |

## Requirements

- Python 3.10 or newer on both sides. tmux-opener uses only the standard library.
- tmux on the host. Popups need tmux 3.2 or newer; older versions open a window instead.
- OpenSSH with Unix socket `RemoteForward` support on the laptop, and key or agent authentication for transfers.
- A desktop opener: `open` on macOS, `xdg-open` on Linux, or `cmd /c start` on Windows.

Optional extras:

- VS Code's `code` CLI with the Remote-SSH extension, to open files at a line
- `fzf` on the host for the [target picker](../guides/picker.md)
- `bat`, `chafa`, `pdftoppm`, `ffmpeg` and `glow` on the host for richer [inline views](../guides/inline-view.md)
- Neovim, VimTeX and `uv` on the host for [LaTeX PDF preview](../guides/vimtex.md)

## On the SSH host

=== "TPM"

    Add the plugin to the host's `~/.tmux.conf` and press <kbd>prefix</kbd> <kbd>I</kbd>:

    ```tmux
    set -g @plugin 'Ramlaoui/tmux-opener'
    ```

    TPM keeps a git checkout, so <kbd>prefix</kbd> <kbd>U</kbd> updates it like any other plugin.

=== "Release archive"

    Download `tmux-opener-server-vX.Y.Z.tar.gz` from the [releases page](https://github.com/Ramlaoui/tmux-opener/releases), then:

    ```sh
    mkdir -p ~/.tmux/plugins
    tar -xzf tmux-opener-server-vX.Y.Z.tar.gz -C ~/.tmux/plugins
    ```

    Load it from `~/.tmux.conf`:

    ```tmux
    run-shell ~/.tmux/plugins/tmux-opener/tmux-opener.tmux
    ```

    Use this for pinned installs on hosts where a git checkout is inconvenient.

## On your laptop

Download `tmux-opener-client-vX.Y.Z.tar.gz` from the [releases page](https://github.com/Ramlaoui/tmux-opener/releases) and install it:

```sh
mkdir -p ~/.local/share ~/.local/bin
tar -xzf tmux-opener-client-vX.Y.Z.tar.gz -C ~/.local/share
ln -sf ~/.local/share/tmux-opener-client/bin/tmux-opener ~/.local/bin/tmux-opener
ln -sf ~/.local/share/tmux-opener-client/bin/tmux-opener-client ~/.local/bin/tmux-opener-client
```

Make sure `~/.local/bin` is on your `PATH`, then [connect to a host](quickstart.md).

!!! tip "Same shortcut on your laptop"

    The desktop can open the dashboard with <kbd>prefix</kbd> <kbd>O</kbd> too. Add this to your local `~/.tmux.conf`:

    ```tmux
    run-shell ~/.local/share/tmux-opener-client/integration/client.tmux
    ```

## Updating

Update both sides together, since new features usually need a newer plugin and a newer client. A TPM install can also be updated from the [dashboards](../guides/dashboards.md#update-the-plugin). After updating by hand:

```sh
tmux-opener restart-client HOST                               # on the laptop
tmux run-shell ~/.tmux/plugins/tmux-opener/tmux-opener.tmux   # on the host
```
