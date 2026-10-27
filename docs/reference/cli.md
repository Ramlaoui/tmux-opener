---
title: Command line
description: The tmux-opener commands on your laptop and the helper scripts on the host.
---

# Command line

## `tmux-opener` (laptop)

| Command | Purpose |
| --- | --- |
| `tmux-opener ssh HOST [-- ssh args]` | Install the bridge for `HOST`, start the client if needed, then run `ssh HOST` |
| `tmux-opener install-host HOST` | Write the managed SSH snippet only; `--start-client` also starts the client |
| `tmux-opener uninstall-host HOST` | Remove the managed snippet |
| `tmux-opener status HOST` | One-line client status |
| `tmux-opener doctor HOST` | Local diagnostics: snippet, socket, client process; `--remote` also pings the bridge from the host over SSH |
| `tmux-opener restart-client HOST` | Replace the client for a host, keeping its options |
| `tmux-opener downloads [HOST]` | Transfers and client information; `--json` for scripts |
| `tmux-opener dashboard [HOST]` | [Browser dashboard](../guides/dashboards.md#in-your-browser); `--no-browser` prints the URL |
| `tmux-opener terminal-dashboard [HOST]` | The same views in the terminal |
| `tmux-opener install-service HOST` | Supervise the client with a launchd agent or systemd user unit |
| `tmux-opener uninstall-service HOST` | Remove that service |

Common options:

| Option | Meaning |
| --- | --- |
| `--dry-run` | Show what would change without writing files or starting processes |
| `--force` | Install the managed forward even when the host already has its own `RemoteForward` |
| `--no-start-client` | `ssh` only: do not start the client |
| `--ssh-config PATH` | SSH config to edit and to use for transfers (default `~/.ssh/config`) |
| `--snippet-dir DIR` | Where managed snippets live (default `~/.ssh/tmux-opener.d`) |
| `--state-dir DIR` | Client sockets and logs (default `~/.local/state/tmux-opener`) |
| `--socket PATH` | A custom client socket |
| `--vscode-file-window`, `--vscode-folder-window` | `new` or `reuse` |
| `--client-verbose` | Log full request payloads; treat these logs as private |
| `--launchd`, `--systemd-user` | Pick the service manager explicitly |

## `tmux-opener-client` (laptop)

The client is usually started for you. Run it directly to preview requests without opening anything:

```sh
tmux-opener-client \
  --socket ~/.local/state/tmux-opener/preview.sock \
  --default-ssh-host HOST \
  --allow-ssh-host HOST \
  --dry-run
```

| Option | Meaning |
| --- | --- |
| `--allow-ssh-host HOST` | Accept file, folder and transfer requests for `HOST` (repeatable) |
| `--allow-url-scheme SCHEME` | Accept another URL scheme besides `http` and `https` |
| `--default-ssh-host HOST` | SSH alias used when a request names none |
| `--pdf-viewer VIEWER` | `auto`, `zathura`, `skim`, `sioyek`, `acrobat` or `system` |
| `--localhost-forward-start-port`, `--localhost-forward-end-port` | Local port range for tunnels (default `18000`–`18999`) |
| `--once` | Serve one request and exit |
| `--verbose` | Log request payloads and commands |

## Scripts on the host

The plugin's `scripts/` folder holds the pieces the key bindings call. You can use them from shell scripts too:

| Script | Purpose |
| --- | --- |
| `tmux-opener-send TARGET` | Send an Open Request for a URL, `localhost:PORT` or path |
| `tmux-opener-dispatch` | What the copy-mode keys pipe the selection into (`--download`, `--save-as`, `--view`, `--upload`) |
| `tmux-opener-pick` | The target picker; `--print-candidates` lists targets without `fzf` |
| `tmux-opener-view [--line N] PATH` | The inline viewer |
| `tmux-opener-status` | The host dashboard |
