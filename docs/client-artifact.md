# tmux-opener client

This archive contains only the local desktop side of tmux-opener:

- `bin/tmux-opener`
- `bin/tmux-opener-client`

It does not include the remote tmux plugin. Install the Remote Opener Plugin
separately on the SSH/tmux hosts where selections should be opened.

## Requirements

- Python 3.10 or newer
- `ssh`
- SSH key/agent authentication for background file downloads and uploads
- A desktop opener: `open` on macOS, `xdg-open` on Linux, or `cmd /c start` on Windows
- Optional: VS Code's `code` CLI for direct Remote-SSH editor launches
- For the `D` save dialog and the upload picker: native macOS support, or `zenity`, `kdialog`, or Python Tk

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

## Native remote PDF preview

The remote VimTeX adapter sends `open_remote_pdf` requests. The client fetches
the PDF over SSH, opens a stable local copy, and replaces it after successful
builds. Transfer failures preserve the previous PDF. SSH aliases and custom SSH
configuration still apply.

The default viewer is Zathura on Linux when installed, Skim on macOS when installed,
or the system PDF handler. Skim receives an explicit reload for the matching open
document after every refresh, without activating the app or opening another window.
Disable Skim's own "Check for file changes" in its Sync preferences when using this
scripted reload, as recommended by [Skim's synchronization documentation](https://sourceforge.net/p/skim-app/wiki/TeX_and_PDF_Synchronization/).
Unsaved Skim notes are preserved; save them before refreshing. macOS may ask for
Automation permission for the client to control Skim. Other viewers must support
automatic file reloading. `--pdf-viewer` or `TMUX_OPENER_PDF_VIEWER` can select
`auto`, `zathura`, `skim`, `sioyek`, `acrobat`, or `system`. The browser and tmux
dashboards detect viewers installed on the desktop, including applications in
`/Applications` and `~/Applications` on macOS. Sioyek uses its command-line
reload with `--nofocus`, targeting the same PDF window. Acrobat on macOS closes
and reopens only the matching cached PDF, restoring its page and zoom; this can
bring that document forward. It refuses to close a document with unsaved edits.
macOS Automation permission is required for scripted Skim and Acrobat refreshes.
Restart the desktop client after updating:

```sh
tmux-opener restart-client HOST
```

For a client started by the SSH wrapper without native service supervision, select
the desktop's default PDF application with:

```sh
TMUX_OPENER_PDF_VIEWER=system tmux-opener restart-client HOST
```

The client reads the preference at startup. For an existing native service, update
its saved command with the same preference:

```sh
TMUX_OPENER_PDF_VIEWER=system tmux-opener install-service HOST
```

The service stores the viewer argument, so the choice survives service restarts.

## Download queue and desktop dashboard

```sh
tmux-opener dashboard
tmux-opener dashboard HOST
tmux-opener terminal-dashboard
tmux-opener downloads HOST
tmux-opener downloads --json
```

The dashboard opens a local browser page showing configured clients, reported
remote host information, and download progress/history. It includes cancel and
retry controls. It binds only to loopback and requires the session token in the
printed URL for API requests. `--no-browser` prints the URL; Ctrl-C stops the
server. The page does not need an external service or web assets.

In Clients, inspect each process, its socket, uptime and recent remote activity.
Use **Restart client** or **Restart all online clients** in the browser. In the
tmux dashboard, `Tab` selects Clients, `j`/`k` selects a process, `r` restarts
that process and `R` restarts all online clients shown. Restart requires the
new client protocol; offline and older clients are never signalled by these
controls. The responding owner acknowledges first, cleans up its socket and
transfers, then re-executes with its original options under the same supervisor.
Active transfers become interrupted and retain partial copies for retry.

The local dashboards can also add a bridge: **Add bridge** in the browser, or
`a` in the terminal dashboard's Clients view, picks a concrete `Host` alias from
`~/.ssh/config` (or `--ssh-config PATH`) and runs
`tmux-opener install-host --start-client HOST`. The server accepts only aliases
listed in that config and runs the CLI without a shell; the remote tmux
dashboard never offers it, since a forwarded session must not edit the desktop's
SSH config.

For the same **prefix + `O`** shortcut in desktop tmux, add this to the local
`.tmux.conf` (or run it directly with `tmux run-shell`):

```tmux
run-shell ~/.local/share/tmux-opener-client/integration/client.tmux
```

It opens the local terminal dashboard, including all desktop clients and their
downloads. The shortcut honors `@tmux_opener_dashboard_key`, and optional
`@tmux_opener_socket`/`@tmux_opener_ssh_host` select a specific local client.

The client runs up to two downloads concurrently and keeps the latest 100
records in a mode-0600 `HOST.downloads.json` beside its socket. Queued and active
records become interrupted after an unexpected restart. A retry creates a new
ID, and cancelled or failed transfers never publish an incomplete destination.
Both the client and the remote plugin must be updated; the host's prefix + `O`
popup reads the same queue through its forwarded socket.

Online clients are responding local processes. Remote host timestamps reflect
plugin reports; they do not imply an active SSH session. Requested status views
include download paths and destinations; normal logs remain redacted.

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

## Download selected files

In remote tmux copy mode, `d` downloads selected files into this machine's
Downloads folder; `D` opens a local save dialog for each file. Downloads run in
the background and use the allowed SSH host. Existing files are preserved:
`d` chooses a numbered name on collision and `D` requires a new filename.
Completion and failures are recorded in the client log, with desktop
notifications through Notification Center on macOS or `notify-send` on Linux.
The `download_notifications` opener setting (`all`, `failures`, `off`) controls
them; the notification text is passed as an argument, never as script source.
Default logs omit paths and SSH stderr; enable client `--verbose` for details.
Downloads honor the client's `--ssh-config` and disable inherited forwarding,
connection sharing, and local commands.

## Upload desktop files

On the host, prefix + `P` asks this client to upload into the pane's current
directory. The client opens a file dialog naming the host and directory; only
the files picked there are sent. The remote request carries just the directory,
never local paths. Each file streams over the same hardened SSH command into a
hidden temporary file, is checked for its full size, and is renamed to a free
name (` (1)`, ` (2)`, ...) without replacing remote files. Uploads share the
download queue, dashboards, cancel/retry and notifications. Folders are not
supported yet.
