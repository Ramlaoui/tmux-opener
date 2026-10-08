# tmux-opener server plugin

This archive contains only the remote tmux side of tmux-opener:

- `tmux-opener.tmux`
- `scripts/tmux-opener-dispatch`
- `scripts/tmux-opener-pick`
- `scripts/tmux-opener-send`
- `scripts/tmux_opener_common.py`
- `integration/vimtex.lua`

It does not include the Local Opener Client or the SSH setup wrapper. Install
and run the local side separately on the desktop machine that should open URLs
and editor targets.

## Install from archive

```sh
mkdir -p ~/.tmux/plugins
tar -xzf tmux-opener-server-vX.Y.Z.tar.gz -C ~/.tmux/plugins
```

Then load it from `.tmux.conf`:

```tmux
run-shell ~/.tmux/plugins/tmux-opener/tmux-opener.tmux
```

## Install with TPM

For normal TPM installs, use the Git repository directly:

```tmux
set -g @plugin 'Ramlaoui/tmux-opener'
```

This archive is mainly for pinned server-side installs on remote hosts where a
Git checkout is inconvenient.

## Remote VimTeX preview

With `uv` installed on the remote host, add this to VimTeX's Neovim `init` configuration:

```lua
dofile(vim.fn.expand('~/.tmux/plugins/tmux-opener/integration/vimtex.lua')).setup()
```

Update the desktop client as well, then connect through `tmux-opener ssh HOST`.
Press `\ll` in remote Neovim to compile and open a local PDF window. Successful
builds update the same cached local PDF without reopening the viewer. The adapter
retains your existing viewer if the bridge lacks remote PDF support.

## Delivery guarantees

Update the desktop client alongside this plugin: bridge health requires a
versioned `tmux-opener-client` ping response. An Open Request succeeds only after
a complete, valid acknowledgement. A dropped connection or missing reply is not
success, and requests are never automatically replayed because the desktop
action may already have happened.

The default deadline for each bridge exchange is five seconds (30 seconds for PDFs), including response
reads. The preliminary health probe uses the same `--timeout` as the Open Request,
so a slow but healthy bridge is not rejected by a shorter hidden timeout.

Sender logs contain action names and delivery status, not selected URLs, paths,
or response payloads. Log files are private to the current user. Explicit
`--print-request` output and terminal fallback hyperlinks still contain the
selected target; do not publish them when opening sensitive links.
