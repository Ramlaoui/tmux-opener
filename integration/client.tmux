#!/usr/bin/env bash
# Optional local tmux binding shipped with the desktop client.
set -euo pipefail

CLIENT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
key="$(tmux show-option -gqv '@tmux_opener_dashboard_key')"
socket_path="$(tmux show-option -gqv '@tmux_opener_socket')"
host="$(tmux show-option -gqv '@tmux_opener_ssh_host')"
printf -v command '%q terminal-dashboard' "$CLIENT_ROOT/bin/tmux-opener"
if [ -n "$socket_path" ]; then
  printf -v socket_arg ' --socket %q' "$socket_path"
  command+="$socket_arg"
fi
if [ -n "$host" ]; then
  printf -v host_arg ' %q' "$host"
  command+="$host_arg"
fi
tmux bind-key "${key:-O}" display-popup -E -d '#{pane_current_path}' -w 90% -h 70% "$command"
