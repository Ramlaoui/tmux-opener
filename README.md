# tmux-opener

Open URLs and remote file paths from tmux copy mode on an SSH host using your
local desktop browser or VS Code Remote-SSH, download files to your desktop, or
upload desktop files into the pane's directory.

Documentation, with recordings of every feature:
[tmux-opener.ramlaoui.org](https://tmux-opener.ramlaoui.org/).

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

The remote side sends structured JSON Open Requests and Download Requests. It never sends arbitrary
shell commands for the local client to execute.

## Requirements

- Python 3.10 or newer on both sides
- tmux on the remote host
- OpenSSH with Unix socket `RemoteForward` support
- A local desktop opener: `open` on macOS or `xdg-open` on Linux
- Optional: VS Code's `code` CLI for direct Remote-SSH editor launches
- Optional: `fzf` for the prefix target picker
- Optional: Neovim, VimTeX, and `uv` on the remote host for LaTeX PDF preview

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

To set up a bridge without connecting yet, pick the host from **Add bridge** on
the Clients page of either local dashboard (see below), or run:

```sh
tmux-opener install-host --start-client HOST
```

Then connect with a plain `ssh HOST`.

Preview the SSH config changes without writing files:

```sh
tmux-opener ssh --dry-run --no-start-client HOST
```

Inside remote tmux copy mode, select a URL or path and press `o`. If `fzf` is
installed, the prefix target picker also uses `o` by default. Press `i` instead
to view the selected file or folder in a tmux popup on the host, without the
bridge or VS Code (see [inline view](#inline-view)).

### VimTeX PDF preview

The repository includes an opt-in Neovim adapter for VimTeX. It only changes
VimTeX when the forwarded tmux-opener bridge is reachable and advertises PDF
support, so ordinary local VimTeX configuration is left alone when no bridge
or an older client is active.

Load it before VimTeX initializes:

```lua
dofile(vim.fn.expand('~/.tmux/plugins/tmux-opener/integration/vimtex.lua')).setup()
```

With lazy.nvim, put the same call in VimTeX's `init` function. If the plugin is
installed somewhere else, use that checkout's absolute path instead.

After connecting with `tmux-opener ssh HOST`, open the `.tex` file in remote
Neovim and press `\ll`. VimTeX compiles on the remote host; on the first
successful build the local client fetches and opens the PDF, and later
successful builds refresh that already-open local viewer. `\lv` opens it on
demand. No web server or manual PDF copying is needed.

The adapter uses the repository's absolute `scripts/tmux-opener-send` path for
VimTeX's general viewer. Compile-success refreshes are sent asynchronously via
`uv run --no-project --no-sync`. Update and restart the local
`tmux-opener-client`, then reconnect the SSH session, when upgrading to a
client that supports PDF requests.

### Download remote files

Select a file path in copy mode and press:

- `d` to download it into the **client machine's Downloads folder** (honoring
  Linux's XDG Downloads setting).
- `D` to choose where to save it using a **save dialog on the client machine**.

You can select several paths, one per line or separated by spaces. Quote paths
containing spaces when combining them on one line. Relative paths use the tmux
pane's working directory; `path:line:column` references are also accepted. URLs
are rejected.

Folders download whole into `Downloads/NAME/`. A glob such as
`runs/exp-42/*.png` (or `runs/**/metrics.csv`) is expanded on the remote host
and downloads the matching files, at most 1000, into a folder named after the
part before the first wildcard (`Downloads/exp-42/`), keeping subpaths. The
client uses `rsync` when both machines have rsync 3, so a failed transfer
resumes on retry; otherwise it streams `tar` over SSH and extracts it safely
(entries escaping the folder are refused, links leaving it and device files are
skipped, as with `rsync --safe-links`).

Downloads run in the background over SSH using the same host alias as the bridge.
The client needs working SSH authentication (an SSH key or agent); transfers
cannot prompt for a password. The tmux message means the download was queued.
Completion and errors appear in the client log and as desktop notifications
(Notification Center on macOS, `notify-send` on Linux); choose all, failures
only or off under Openers in either dashboard. Default logs omit paths and SSH stderr;
enable client `--verbose` for transfer details. Transfers honor the client's
custom SSH config and disable inherited forwards and shared connections.
Files appear at their destination only after
a successful transfer. Transfers are resumable: received bytes are kept in a
private partial copy under `~/.cache/tmux-opener/partial`, so a dropped SSH
connection (retried automatically twice), a cancel, a client restart or a retry
continues from where it stopped. The client resumes only while the remote
file's size and modification time are unchanged; otherwise it starts over.
Unused partial copies are deleted after 7 days. `d` adds ` (1)`, ` (2)`, etc. if a name already exists.
For `D`, choose a new filename; existing files are preserved. With several paths,
`D` asks once per file. Canceling a dialog skips that file.

On macOS, `D` uses the native save dialog. On Linux it uses `zenity` or `kdialog`,
with Python Tk as a fallback. Windows uses Python Tk. Downloads require the
client bridge; they do not use the same-host opener fallback.

### Upload desktop files

Press **prefix + `P`** in a pane on the host. A file dialog opens on the
**client machine**; the files you pick are copied into that pane's current
directory. Pick several files to upload them together; folders are not
supported yet.

The host only names the destination directory. It cannot choose, list or read
desktop files: nothing is sent unless you pick it in the dialog, which shows the
host and directory it uploads to. Uploads never replace remote files: a name
that already exists gets ` (1)`, ` (2)`, etc., as downloads do. Each file is
written to a hidden temporary file in the directory and renamed only once every
byte arrived, so a failed or cancelled upload leaves nothing behind.

Uploads use the same SSH host alias, authentication requirements, queue,
dashboards and notifications as downloads. Retrying a failed upload sends the
files that did not arrive, without asking again. On macOS the picker is the
native open dialog; on Linux it uses `zenity` or `kdialog`, with Python Tk as a
fallback.

### Download queue and dashboards

Press **prefix + `O`** (capital O) on the host to open the live tmux dashboard.
It shows the desktop client's machine, user, OS and process, the current remote
host/pane information, and recent downloads with progress bars. Use the arrow
keys or `j`/`k` to select a download, `c` to cancel it, `r` to retry a failed,
cancelled or interrupted transfer, `Tab` to cycle through Transfers, Clients and
[Openers](#opener-rules), and `q` to close the popup. In Clients, use `r` to
restart the selected client or `R` to restart all online clients shown. Configure the
shortcut with:

```tmux
set -g @tmux_opener_dashboard_key 'O'
```

On the desktop, open the browser dashboard or pull a snapshot:

```sh
tmux-opener dashboard          # all configured desktop clients
tmux-opener dashboard HOST     # one host's client
tmux-opener terminal-dashboard # local clients in a terminal
tmux-opener downloads HOST
tmux-opener downloads --json
```

The browser dashboard runs on a temporary loopback port and supports the same
cancel/retry actions, plus a Clients page and an Openers settings page. It polls local client sockets, including custom sockets in
managed SSH snippets, and displays configured offline clients. `--no-browser`
prints its local URL instead of opening a browser. Keep the command running
while using the page; Ctrl-C closes the dashboard server.

The Clients page shows the desktop process and recent host activity, with
**Restart client** and **Restart all online clients** controls. The local
dashboards manage all discovered desktop clients; a remote tmux dashboard
manages only the client reached through its forwarded bridge. Offline and older
clients remain visible but cannot be restarted through the dashboard. Restarts
preserve startup options and native service supervision. Active transfers are
interrupted; retry them from Transfers to resume available partial copies.

**Add bridge** on the browser Clients page, or `a` in the terminal dashboard's
Clients view, lists the concrete `Host` aliases in `~/.ssh/config` (following
`Include`; wildcard and negated patterns are skipped) and marks hosts that
already have a bridge. Type to filter, then pick a host: the dashboard runs
`tmux-opener install-host --start-client HOST`, which writes the managed snippet
and starts the client, and you then connect with `ssh HOST`. An existing
conflicting `RemoteForward` is reported rather than overwritten. Pass
`--ssh-config PATH` to either dashboard to list another config. The remote tmux
dashboard cannot add bridges: a forwarded session must not edit the desktop's
SSH config.

The desktop can use the same **prefix + `O`** shortcut. Add this to the local
desktop's `.tmux.conf` after installing the client archive:

```tmux
run-shell ~/.local/share/tmux-opener-client/integration/client.tmux
```

For a source checkout, use its `integration/client.tmux` path instead. Reload
the file with `tmux run-shell PATH/TO/integration/client.tmux` to apply it to an
existing tmux server. This opens the local terminal dashboard, which aggregates
the desktop clients. The regular tmux plugin also falls back to this local view
when there is no forwarded bridge and the desktop `tmux-opener` CLI is on PATH.

Transfers have stable IDs and move through queued, choosing a save destination,
downloading, completed, failed or cancelled states. Two transfers can run at once.
The client stores the latest 100 records in a private `HOST.downloads.json` file
beside its socket. After a restart, unfinished records are marked interrupted;
retrying creates a new transfer without changing the old record. Progress shows
received bytes and percentages when the plugin supplied a file size. The source
file can change during a transfer, so completion is confirmed by the final state.

Client **online/offline** means the local client responded to a status request.
Remote host information is reported by the plugin when downloading or viewing
the host dashboard; its timestamp shows recent activity, not an active SSH
connection count. The tmux view covers its forwarded client; the desktop view
aggregates clients on that desktop. Download paths appear in these requested
status views while ordinary logs stay redacted.

Both sides must be updated for queue status. After updating both installations, restart the client with
`tmux-opener restart-client HOST` and reload the tmux plugin:

```sh
tmux run-shell ~/.tmux/plugins/tmux-opener/tmux-opener.tmux
```

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
- Copy-mode download keys: `d` (Downloads), `D` (save dialog)
- Copy-mode inline view key: `i`
- Prefix target picker key: `o`
- Prefix upload key: `P` (`U` is taken by TPM's plugin update)
- Remote socket: `/tmp/tmux-opener-$USER.sock`
- Remote folders open in a new VS Code Remote-SSH window
- Remote files open in a new VS Code Remote-SSH window rooted at the pane cwd,
  unless an [opener rule](#opener-rules) matches
- Remote `localhost:PORT` URLs open through a local SSH `-L` tunnel
- Fallback: if the bridge is unavailable, copy-mode uses same-host `open` or
  `xdg-open`
- Route feedback: tmux briefly displays which route was used

Common tmux options:

```tmux
set -g @tmux_opener_key 'o'
set -g @tmux_opener_download_key 'd'
set -g @tmux_opener_save_as_key 'D'
set -g @tmux_opener_view_key 'i'
set -g @tmux_opener_picker_key 'o'
set -g @tmux_opener_upload_key 'P'
set -g @tmux_opener_fallback 'auto' # or local, command, none
```


The copy-mode key does not try to infer whether the pane is SSH. It pings the
forwarded socket; a successful ping means bridge path, and a failed ping means
fallback path.

```sh
tmux-opener-client --allow-ssh-host HOST
```

### Opener rules

Desktop settings live in `~/.config/tmux-opener/settings.json` (or
`$XDG_CONFIG_HOME/tmux-opener/settings.json`) and apply to every client on that
desktop without a restart. Edit them on the **Openers** page of
`tmux-opener dashboard`, or with `Tab` in either tmux dashboard: `←`/`→` change
the selected value, `a` adds a rule, `x` deletes it and `J`/`K` reorder.

Rules map remote **file** paths to an opener; the first match wins and folders
always open in VS Code:

| Opener | Effect |
| --- | --- |
| `vscode` | VS Code Remote-SSH at the selected line (default) |
| `tmux` | Inline: show the file in a tmux popup on the remote host (shown as **Inline**) |
| `preview` | Copy into `~/.cache/tmux-opener/preview/` and open locally (PDFs use the PDF viewer below) |
| `download` | Queue a normal download into Downloads |

```json
{
  "rules": [
    {"pattern": "*.log", "opener": "tmux"},
    {"pattern": "*.pdf", "opener": "preview"},
    {"pattern": "*/figures/*.png", "opener": "preview"},
    {"pattern": "*.ckpt", "opener": "download"}
  ],
  "vscode_file_window": "new",
  "vscode_folder_window": "new",
  "pdf_viewer": "auto",
  "download_notifications": "all"
}
```

Patterns are case-insensitive shell globs; a pattern without `/` matches the
file name, otherwise the full remote path. `pdf_viewer` is `auto`, `zathura`,
`skim`, `sioyek`, `acrobat` or `system`; the dashboards offer installed viewers.
Sioyek refreshes without taking focus. Acrobat on macOS reopens the matching PDF
at the same page and zoom, and refuses to refresh unsaved edits.
Window policies are `new` or `reuse`. `download_notifications` is `all`,
`failures` or `off`; local previews are never announced. Command-line flags
(`--vscode-file-window`, `--vscode-folder-window`, `--pdf-viewer`) and
`TMUX_OPENER_PDF_VIEWER` override the file.

Settings never contain commands, because a forwarded remote session can edit
them. For the same reason `preview` only accepts documents, images, audio and
video (`.pdf`, `.md`, `.txt`, `.csv`, `.png`, `.mp4`, …); formats that can run
code when opened, such as `.html`, `.svg`, `.command` or office files, are
refused. Use `download` for those.

### Inline view

The `tmux` opener and the `i` copy-mode key show a file in a 90% tmux popup on
the remote host; `q` closes it. The viewer uses what the host has installed:

- text: `bat` (or `batcat`) with the selected line highlighted, otherwise `less`
- `.csv`/`.tsv`: aligned columns with the header pinned while scrolling (first
  5000 rows); `j`/`k`, `space`/`b`, `h`/`l`, `g`/`G` and `/` search
- `.md`: `glow` when installed, otherwise a built-in renderer (headings, lists,
  code blocks, tables, links)
- `.json`: `jq`, otherwise Python's `json.tool`
- images: `chafa` or `timg` when installed, otherwise file details; in Ghostty or kitty, chafa draws real pixels
  in a tmux window, since tmux keeps graphics out of popups
- `.pdf`: in Ghostty or kitty, pages drawn in pixels by `pdftoppm` and `chafa`
  (`space`/`b` or arrows change page, `g`/`G` first/last, `path:N` opens page N);
  otherwise the text from `pdftotext`
- binary files: file type and size instead of raw bytes
- folders: a file browser with a preview pane in wide panes. `j`/`k` or arrows
  move, Enter opens a folder or previews a file (closing the preview returns to
  the list), `h`/`←` or the `../` row goes up, `space` marks files and folders
  (across folders), `a` marks everything, `d` downloads the marked entries or the
  one under the cursor (`D` asks where to save), `/` searches names, `.` shows
  hidden files. In Ghostty or kitty, folders open in a window so previews draw
  pixels

`path:LINE` selections open at that line. Files over 20 MiB skip highlighting
and stream through `less`. tmux older than 3.2 has no popups, so the view opens
in a new window instead. An `o` press only uses the Inline rule when the remote
plugin is new enough to show popups; older plugins and VimTeX keep VS Code.

## Troubleshooting

Useful commands:

```sh
tmux-opener doctor HOST
tmux-opener doctor HOST --remote
tmux-opener status HOST
tmux-opener restart-client HOST
```

For automatic client recovery after an unexpected exit, explicitly install the
native user service with `tmux-opener install-service HOST`. See
[client lifecycle and supervision](docs/client-artifact.md#optional-native-supervision)
for preview, configuration and uninstall commands. Restart only the affected
client; deleting socket files or terminating a shared SSH master is not normal
recovery.

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

Run an isolated preview listener without opening apps (not the live bridge):

```sh
tmux-opener-client \
  --socket ~/.local/state/tmux-opener/preview.sock \
  --default-ssh-host HOST \
  --allow-ssh-host HOST \
  --localhost-forward-start-port 18000 \
  --localhost-forward-end-port 18999 \
  --dry-run
```


## Development

Run the test suite:

```sh
uv run --frozen --group dev pytest
```

Release packaging and tag flow are documented in
[docs/releasing.md](docs/releasing.md).
