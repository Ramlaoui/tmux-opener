---
title: Troubleshooting
description: Diagnose a bridge that does not answer, files that open on the wrong machine, and transfers that fail.
---

# Troubleshooting

Start with the doctor on your laptop:

```sh
tmux-opener doctor HOST           # snippet, socket and client process
tmux-opener doctor HOST --remote  # also ping the bridge from the host (needs python3 there)
tmux-opener status HOST
```

## The URL opened on the host, not on my laptop

tmux showed *opened via same-host fallback*, so the bridge did not answer.

- Connect with `tmux-opener ssh HOST` once, or `tmux-opener install-host --start-client HOST`, so the SSH config has the forward.
- A tmux server started **before** the bridge existed still works: the plugin pings the socket on every key press. But the SSH session you attach from must carry the forward, so reconnect after installing.
- If `ssh` warns that remote port forwarding failed, a stale socket from an earlier session may be in the way. The host's `sshd_config` needs `StreamLocalBindUnlink yes` to replace it.
- Set `@tmux_opener_fallback 'none'` to see an error instead of a silent local open.

## The client died or is stuck

```sh
tmux-opener restart-client HOST
```

Restart only the affected client. Deleting socket files or closing a shared SSH master connection is not normal recovery. For automatic restarts, install the native service with `tmux-opener install-service HOST` ([details](client-artifact.md#optional-native-supervision)).

## Files open in VS Code on the wrong machine, or not at all

- The laptop needs the `code` command and the Remote-SSH extension.
- The SSH alias VS Code uses must reach the host. If the host is known by another alias on your laptop, set `@tmux_opener_ssh_host` on the host.
- Requests for hosts the client was not started for are refused. Add them with `--allow-ssh-host`.

## Downloads fail

- Transfers run without a terminal and cannot ask for a password: use keys or an agent.
- `tmux-opener downloads HOST` shows the error for each transfer; retry with <kbd>r</kbd> in the [dashboard](guides/dashboards.md).
- A transfer that stops part-way resumes on retry while the remote file is unchanged.

## A localhost URL does not load

- The service must listen on the host's loopback interface on that port.
- `tmux-opener doctor HOST` lists the client's active tunnels. If all ports in `18000`–`18999` are busy, choose another range with `--localhost-forward-start-port` and `--localhost-forward-end-port`.

## Logs

| Machine | Log |
| --- | --- |
| laptop | `~/.local/state/tmux-opener/HOST.log` |
| host | `~/.local/state/tmux-opener/sender.log` |

Normal logs omit targets. Restart the client with `tmux-opener restart-client --client-verbose HOST` to log full requests, and redact before sharing.
