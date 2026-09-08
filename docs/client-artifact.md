# tmux-opener client

This archive contains only the local desktop side of tmux-opener:

- `bin/tmux-opener`
- `bin/tmux-opener-client`

It does not include the remote tmux plugin. Install the Remote Opener Plugin
separately on the SSH/tmux hosts where selections should be opened.

## Requirements

- Python 3.10 or newer
- `ssh`
- A desktop opener: `open` on macOS, `xdg-open` on Linux, or `cmd /c start` on Windows
- Optional: VS Code's `code` CLI for direct Remote-SSH editor launches

## Install from archive

```sh
mkdir -p ~/.local/share ~/.local/bin
tar -xzf tmux-opener-client-vX.Y.Z.tar.gz -C ~/.local/share
ln -sf ~/.local/share/tmux-opener-client/bin/tmux-opener ~/.local/bin/tmux-opener
ln -sf ~/.local/share/tmux-opener-client/bin/tmux-opener-client ~/.local/bin/tmux-opener-client
```

Make sure `~/.local/bin` is on `PATH`.

## Start the bridge for a host

```sh
tmux-opener ssh HOST
```

The wrapper installs the managed SSH `RemoteForward` snippet, starts
`tmux-opener-client` when needed, and then execs `ssh HOST`.

Preview the generated SSH config changes without writing files:

```sh
tmux-opener ssh --dry-run --no-start-client HOST
```

The local client only accepts structured Open Requests. Remote file/editor
requests are rejected unless the client was started for the target host, or was
explicitly started with `--allow-ssh-host HOST`.

## Safe client ownership

Each client holds a lifetime lock beside its socket; wrapper lifecycle operations
use a separate operation lock. `restart-client HOST` verifies the responding
owner before signalling it and waits for ownership release (or legacy process
exit), not a failed ping. A timeout or permission error preserves the socket.
An unresponsive legacy client must be stopped by its original launcher before
replacement; tmux-opener never searches for processes to kill.

Only a refused connection to an owned Unix socket permits stale cleanup.
Symlinks, ordinary files and foreign sockets are rejected. Shutdown only removes
the socket inode this client bound, so an old client cannot unlink a replacement.
Keep socket directories private; ownership and operation lock files are persistent
coordination objects and must not be removed while any client or wrapper runs.
