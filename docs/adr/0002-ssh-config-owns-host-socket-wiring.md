# SSH config owns host socket wiring

The first `tmux-opener ssh HOST` run installs a managed SSH config include and per-host snippet, then later ordinary `ssh HOST` commands inherit the Local Opener Bridge. This keeps remote tmux configuration host-agnostic: the SSH connection selects the forwarded local socket, and the Local Opener Client attached to that socket supplies the VS Code Remote-SSH alias.
