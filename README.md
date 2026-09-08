# tmux-opener

Open URLs and remote file paths from tmux copy mode on an SSH host using your
local desktop browser or VS Code Remote-SSH.

## Contents

- [How It Works](#how-it-works)
- [Requirements](#requirements)
- [Install](#install)
- [Connect And Use](#connect-and-use)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

## How It Works

```text
remote tmux selection
  -> tmux-opener remote plugin
  -> bridge available?
     yes -> SSH RemoteForward Unix socket -> local opener client
     no  -> same-host fallback opener
```

The remote side sends structured JSON Open Requests. It never sends arbitrary
shell commands for the local client to execute.

## Requirements

- Python 3.10 or newer on both sides
- tmux on the remote host
- OpenSSH with Unix socket `RemoteForward` support
- A local desktop opener: `open` on macOS or `xdg-open` on Linux
- Optional: VS Code's `code` CLI for direct Remote-SSH editor launches
- Optional: `fzf` for the prefix target picker

## Install

tmux-opener has two parts:

- the **Remote Opener Plugin** on the SSH/tmux host
- the **Local Opener Client** on the desktop machine

### Remote tmux plugin

With TPM, add this to the remote host's `.tmux.conf`:

```tmux
set -g @plugin 'Ramlaoui/tmux-opener'
```

For a release archive install:

```sh
mkdir -p ~/.tmux/plugins
tar -xzf tmux-opener-server-vX.Y.Z.tar.gz -C ~/.tmux/plugins
```

Then load it from `.tmux.conf`:

```tmux
run-shell ~/.tmux/plugins/tmux-opener/tmux-opener.tmux
```

### Local desktop client

Install the client archive on the desktop machine:

```sh
mkdir -p ~/.local/share ~/.local/bin
tar -xzf tmux-opener-client-vX.Y.Z.tar.gz -C ~/.local/share
ln -sf ~/.local/share/tmux-opener-client/bin/tmux-opener ~/.local/bin/tmux-opener
ln -sf ~/.local/share/tmux-opener-client/bin/tmux-opener-client ~/.local/bin/tmux-opener-client
```

Make sure `~/.local/bin` is on `PATH`.

## Connect And Use

Run the wrapper from the local desktop machine:

```sh
tmux-opener ssh HOST
```

The first run installs a managed SSH config snippet, backs up `~/.ssh/config`
before changing it, starts a local `tmux-opener-client` when needed, and then
execs `ssh HOST`. After that, ordinary `ssh HOST` inherits the same bridge from
`~/.ssh/config`.

Preview the SSH config changes without writing files:

```sh
tmux-opener ssh --dry-run --no-start-client HOST
```

Inside remote tmux copy mode, select a URL or path and press `o`. If `fzf` is
installed, the prefix target picker also uses `o` by default.

Remote localhost URLs are treated as remote services, not local desktop
services. For example:

```sh
tmux-opener-send localhost:8080
tmux-opener-send http://127.0.0.1:8888/lab?token=abc
```

The Local Opener Client starts or reuses a supervised auxiliary SSH connection
and opens a rewritten local URL, for example `http://127.0.0.1:18080`.
It establishes a private control master using the original SSH configuration
with **all inherited forwarding disabled**, then requests only the desired
`127.0.0.1:18080:localhost:8080` local forward over that private control socket.
This auxiliary connection never requests the managed bridge `RemoteForward`.

Host aliases, authentication, identities, host-key checking, `Include`/`Match`,
and `ProxyJump`/`ProxyCommand` remain evaluated by OpenSSH in their original
configuration context. A custom wrapper `--ssh-config` is passed to the client;
standalone clients can supply the same option. The control-only forwarding
operation reads no SSH config and cannot fall back to a new connection.

The client verifies the local listener before opening the URL. It removes the
private control socket after setup and terminates the auxiliary process on
startup failure or client shutdown. No separate persistent master is left
behind. Both setup stages are bounded; slow authentication can fail explicitly
rather than leaving an unmanaged connection.

Remove a managed host snippet with:

```sh
tmux-opener uninstall-host HOST
```

## Configuration

Defaults:

- Copy-mode key: `o`
- Prefix target picker key: `o`
- Remote socket: `/tmp/tmux-opener-$USER.sock`
- Remote folders open in a new VS Code Remote-SSH window
- Remote files open in a new VS Code Remote-SSH window rooted at the pane cwd
- Remote `localhost:PORT` URLs open through a local SSH `-L` tunnel
- Fallback: if the bridge is unavailable, copy-mode uses same-host `open` or
  `xdg-open`
- Route feedback: tmux briefly displays which route was used

Common tmux options:

```tmux
set -g @tmux_opener_key 'o'
set -g @tmux_opener_picker_key 'o'
set -g @tmux_opener_fallback 'auto' # or local, command, none
```


The copy-mode key does not try to infer whether the pane is SSH. It pings the
forwarded socket; a successful ping means bridge path, and a failed ping means
fallback path.

```sh
tmux-opener-client --allow-ssh-host HOST
```

## Troubleshooting

Useful commands:

```sh
tmux-opener doctor HOST
tmux-opener status HOST
tmux-opener restart-client HOST
```

Logs:

- Local client: `~/.local/state/tmux-opener/HOST.log`
- Remote sender: `~/.local/state/tmux-opener/sender.log`

The client reads each request under a two-second absolute deadline and a 1 MiB
limit. Up to 32 peer connections are admitted; desktop dispatch is serialized
with one waiting request. Health checks remain responsive during partial reads
and slow dispatch. Requests rejected as busy are not automatically retried.

Normal client logs identify actions without recording request targets. `--verbose`
(or `tmux-opener ssh --client-verbose`) explicitly enables sensitive request and
command logging: URLs, query tokens, remote paths, and SSH diagnostics may appear.
Treat verbose logs as private and redact them before sharing.

Preview launches without opening apps (add `--verbose` to inspect full commands):

```sh
pkill -f tmux-opener-client || true
tmux-opener-client \
  --socket ~/.local/state/tmux-opener/HOST.sock \
  --default-ssh-host HOST \
  --allow-ssh-host HOST \
  --localhost-forward-start-port 18000 \
  --localhost-forward-end-port 18999 \
  --dry-run
```

Include full request payloads in the local log:

```sh
pkill -f tmux-opener-client || true
tmux-opener ssh --client-verbose HOST
tail -f ~/.local/state/tmux-opener/HOST.log
```

## Development

Run the test suite:

```sh
uv run --frozen --group dev pytest
```

Release packaging and tag flow are documented in
[docs/releasing.md](docs/releasing.md).
