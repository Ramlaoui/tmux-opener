# tmux-opener server plugin

This archive contains only the remote tmux side of tmux-opener:

- `tmux-opener.tmux`
- `scripts/tmux-opener-dispatch`
- `scripts/tmux-opener-pick`
- `scripts/tmux-opener-send`
- `scripts/tmux-opener-status`
- `scripts/tmux_opener_common.py`
- `integration/vimtex.lua`

It does not include the Local Opener Client or the SSH setup wrapper. Install
and run the local side separately on the desktop machine that should open URLs
and editor targets.

In copy mode, select file paths and press `d` to download to the client Downloads
folder, or `D` to open a save dialog on the client. Both require an updated Local
Opener Client and an available bridge. Several paths can be selected, one per
line or space-separated (quote filenames containing spaces).

Press the tmux prefix followed by `P` to pick files on the client and upload
them into the pane's current directory (`@tmux_opener_upload_key`). The client
must advertise the `upload_files` capability; older clients are refused with a
message.

## Host dashboard

Press the tmux prefix followed by `O` to open the host dashboard. It reports
the local client machine, the most recent host metadata reported by the current
terminal, and client mediated file transfers. The host activity label means
that a terminal recently reported metadata; it does not claim that an SSH
connection is currently active.

The dashboard uses the version 1 `get_status` request and the same forwarded
Unix socket as the other plugin commands. It refreshes about once per second.
Use the arrow keys (or `j`/`k`) to select a transfer, `c` to request
cancellation, `r` to retry a failed, cancelled, or interrupted transfer, and
`q` to close the popup. `Tab` cycles through Transfers, Clients and Openers.
The Clients view reports the connected desktop opener process; `r` restarts it
and `R` restarts all online clients shown (only the bridged client in remote
mode). Restarts preserve the client's options and native supervisor. Active
transfers become interrupted and can be retried. A remote dashboard cannot
restart other desktop clients.

The `--once` and `--json` modes are available for noninteractive checks:

```sh
scripts/tmux-opener-status --once
scripts/tmux-opener-status --json
scripts/tmux-opener-status --local --once
```

The request carries the source pane's `TMUX_PANE`, current working directory,
hostname, user, and operating system. Configure the dashboard key or the
socket and SSH host in tmux as usual:

```tmux
set -g @tmux_opener_dashboard_key 'O'
set -g @tmux_opener_socket '/tmp/tmux-opener-myuser.sock'
set -g @tmux_opener_ssh_host 'cluster'
```

The dashboard requires a client that implements the status contract. An older
client is reported as unsupported in the dashboard and does not make the
popup disappear; bridge failures remain visible until the bridge recovers or
the user quits.

Install the same plugin in the desktop tmux session to use the prefix `O`
there as well. The desktop entrypoint runs the local aggregation mode over
all configured client sockets (`~/.local/state/tmux-opener` and
`~/.ssh/tmux-opener.d`); it includes reachable and offline aliases and routes
transfer actions back to the owning client. An interactive remote popup falls
back to that desktop entrypoint when its forwarded bridge is unavailable.

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
