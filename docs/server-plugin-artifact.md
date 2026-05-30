# tmux-opener server plugin

This archive contains only the remote tmux side of tmux-opener:

- `tmux-opener.tmux`
- `scripts/tmux-opener-dispatch`
- `scripts/tmux-opener-pick`
- `scripts/tmux-opener-send`
- `scripts/tmux_opener_common.py`

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
