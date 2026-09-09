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

## Optional native supervision

Service installation is explicit, never a side effect of connecting:

```sh
tmux-opener install-service HOST --dry-run
tmux-opener install-service HOST --ssh-config /path/to/ssh-config --vscode-file-window reuse
tmux-opener restart-client HOST
tmux-opener uninstall-service HOST
```

The default is a launchd LaunchAgent on macOS and a systemd user service on Linux.
`--launchd` and `--systemd-user` select a backend explicitly (also useful to preview
either format). Installation writes a mode-0600 configuration and log, starts the
service with `launchctl bootstrap` or `systemctl --user enable --now`, and checks
client readiness. It requires an active GUI login/user service manager; no root,
system service or Linux lingering is configured. The captured PATH allows desktop
editor discovery. Host allowlisting, editor window settings and custom SSH config
are preserved; rerun installation to change installed options.

The launchd job uses `ProcessType=Interactive` because it handles user-triggered
desktop actions over a Unix socket, not XPC transactions. This avoids launchd's
default background resource throttling; it does not prevent the Mac from sleeping.
Rerun `install-service HOST` to update an existing job's configuration.

`restart-client` and automatic ensure use the installed supervisor, never a second
detached launcher. Reinstallation/uninstallation stops supervision before stopping
the owner, preventing restart races. Uninstallation removes only the service
configuration; SSH snippets, logs and coordination locks remain. Service names are
derived from the absolute socket path, so use the same `--socket`/`--state-dir` when
managing a custom installation. An unresponsive owner is never replaced on a
health timeout; inspect the native service manager and log before retrying.

## Diagnose the existing bridge

```sh
tmux-opener doctor HOST
tmux-opener doctor HOST --remote --ssh-config /path/to/ssh-config
```

Local doctor checks configuration and the local ping without connecting to a
remote host. Local health checks allow three seconds for a complete reply rather
than treating a brief scheduling delay as a dead client. Startup/readiness polling
remains bounded by its enclosing deadline.

`--remote` explicitly opens a bounded, noninteractive BatchMode SSH
session and sends a framed protocol ping to the *existing* remote socket. It
requires remote `python3`. Diagnostic SSH disables forwarding, connection sharing
and local commands: it does not create a socket, change a master or repair the
bridge. The returned process-instance identity must match the expected local
client, detecting sockets forwarded to another desktop. Both endpoints must run
the current client protocol; upgrade/restart a legacy client first.

Exit statuses: 0 healthy, 1 local configuration/client prerequisite failed,
2 diagnostic SSH transport failure/timeout, 3 remote ping/execution/protocol
failure, 4 wrong desktop/client instance. Failures suggest the next action without
printing remote request payloads or SSH stderr. If the local client restarts
during doctor, rerun the diagnostic to obtain a fresh identity comparison.
