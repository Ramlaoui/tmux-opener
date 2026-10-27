---
title: Keys and options
description: Every tmux key binding and @tmux_opener option, with defaults.
---

# Keys and options

## Keys

| Key | Where | Action |
| --- | --- | --- |
| <kbd>o</kbd> | copy mode | [Open](../guides/open.md) the selection |
| <kbd>i</kbd> | copy mode | [View](../guides/inline-view.md) the selection on the host |
| <kbd>d</kbd> | copy mode | [Download](../guides/downloads.md) the selection to Downloads |
| <kbd>D</kbd> | copy mode | Download through a save dialog on the laptop |
| <kbd>prefix</kbd> <kbd>o</kbd> | normal | [Target picker](../guides/picker.md) |
| <kbd>prefix</kbd> <kbd>P</kbd> | normal | [Upload](../guides/uploads.md) into the pane's directory |
| <kbd>prefix</kbd> <kbd>O</kbd> | normal | [Dashboard](../guides/dashboards.md) |

Copy-mode keys are bound in both `copy-mode` and `copy-mode-vi`.

## Options

Set options in `~/.tmux.conf` before the plugin loads.

```tmux
set -g @tmux_opener_key 'o'
set -g @tmux_opener_view_key 'i'
set -g @tmux_opener_download_key 'd'
set -g @tmux_opener_save_as_key 'D'
set -g @tmux_opener_picker_key 'o'
set -g @tmux_opener_upload_key 'P'
set -g @tmux_opener_dashboard_key 'O'
```

| Option | Default | Meaning |
| --- | --- | --- |
| `@tmux_opener_key` | `o` | Copy-mode open key |
| `@tmux_opener_view_key` | `i` | Copy-mode inline view key |
| `@tmux_opener_download_key` | `d` | Copy-mode download key |
| `@tmux_opener_save_as_key` | `D` | Copy-mode "download to…" key |
| `@tmux_opener_picker_key` | `o` | Prefix key for the target picker |
| `@tmux_opener_upload_key` | `P` | Prefix key for uploads (TPM uses <kbd>U</kbd>) |
| `@tmux_opener_dashboard_key` | `O` | Prefix key for the dashboard |
| `@tmux_opener_socket` | `/tmp/tmux-opener-$USER.sock` | Forwarded bridge socket on the host |
| `@tmux_opener_ssh_host` | unset | SSH alias the laptop uses to reach this host, when it differs from the one the client was started for |
| `@tmux_opener_fallback` | `auto` | `auto`, `local`, `command` or `none`; see [fallback](../guides/open.md#when-there-is-no-bridge) |
| `@tmux_opener_fallback_command` | unset | Command run with the selection when the fallback is `command` |
| `@tmux_opener_bridge_policy` | `always` | `always` tries the bridge, `local` never does, `ssh-client-only` only when the tmux environment has `SSH_CONNECTION` or `SSH_CLIENT` |
| `@tmux_opener_route_feedback` | `auto` | `auto` and `always` show the route used, `never` stays quiet |
| `@tmux_opener_picker_history_lines` | visible pane | Scrollback lines the picker also scans |
| `@tmux_opener_picker_prompt` | `open> ` | Picker prompt |
| `@tmux_opener_picker_fzf_height` | `40%` | Picker `fzf --height` |

## Files

| Path | Machine | Contents |
| --- | --- | --- |
| `~/.ssh/tmux-opener.d/HOST.conf` | laptop | Managed `RemoteForward` snippet, included from `~/.ssh/config` |
| `~/.local/state/tmux-opener/HOST.sock` | laptop | Client socket (mode `0600`) |
| `~/.local/state/tmux-opener/HOST.log` | laptop | Client log |
| `~/.config/tmux-opener/settings.json` | laptop | [Opener rules](../guides/opener-rules.md) |
| `~/.cache/tmux-opener/partial/` | laptop | Resumable partial downloads |
| `/tmp/tmux-opener-$USER.sock` | host | Forwarded end of the bridge |
| `~/.local/state/tmux-opener/sender.log` | host | Sender log |
