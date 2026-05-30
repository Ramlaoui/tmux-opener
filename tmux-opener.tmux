#!/usr/bin/env bash
set -euo pipefail

CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

shell_quote() {
  printf '%q' "$1"
}

key="$(tmux show-option -gqv '@tmux_opener_key')"
picker_key="$(tmux show-option -gqv '@tmux_opener_picker_key')"
socket_path="$(tmux show-option -gqv '@tmux_opener_socket')"
ssh_host="$(tmux show-option -gqv '@tmux_opener_ssh_host')"
fallback="$(tmux show-option -gqv '@tmux_opener_fallback')"
fallback_command="$(tmux show-option -gqv '@tmux_opener_fallback_command')"
bridge_policy="$(tmux show-option -gqv '@tmux_opener_bridge_policy')"
route_feedback="$(tmux show-option -gqv '@tmux_opener_route_feedback')"
picker_history_lines="$(tmux show-option -gqv '@tmux_opener_picker_history_lines')"
picker_prompt="$(tmux show-option -gqv '@tmux_opener_picker_prompt')"
picker_fzf_height="$(tmux show-option -gqv '@tmux_opener_picker_fzf_height')"

if [ -z "$key" ]; then
  key="o"
fi
if [ -z "$picker_key" ]; then
  picker_key="o"
fi

cmd="TMUX_OPENER_CWD=#{q:pane_current_path}"
if [ -n "$socket_path" ]; then
  cmd="$cmd TMUX_OPENER_SOCKET=$(shell_quote "$socket_path")"
fi
if [ -n "$ssh_host" ]; then
  cmd="$cmd TMUX_OPENER_SSH_HOST=$(shell_quote "$ssh_host")"
fi
if [ -n "$fallback" ]; then
  cmd="$cmd TMUX_OPENER_FALLBACK=$(shell_quote "$fallback")"
fi
if [ -n "$fallback_command" ]; then
  cmd="$cmd TMUX_OPENER_FALLBACK_COMMAND=$(shell_quote "$fallback_command")"
fi
if [ -n "$bridge_policy" ]; then
  cmd="$cmd TMUX_OPENER_BRIDGE_POLICY=$(shell_quote "$bridge_policy")"
fi
if [ -n "$route_feedback" ]; then
  cmd="$cmd TMUX_OPENER_ROUTE_FEEDBACK=$(shell_quote "$route_feedback")"
fi
cmd="$cmd $(shell_quote "$CURRENT_DIR/scripts/tmux-opener-dispatch")"

tmux bind-key -T copy-mode-vi "$key" send-keys -X copy-pipe-and-cancel "$cmd"
tmux bind-key -T copy-mode "$key" send-keys -X copy-pipe-and-cancel "$cmd"

picker_cmd="TMUX_OPENER_CWD=\"\$PWD\""
if [ -n "$socket_path" ]; then
  picker_cmd="$picker_cmd TMUX_OPENER_SOCKET=$(shell_quote "$socket_path")"
fi
if [ -n "$ssh_host" ]; then
  picker_cmd="$picker_cmd TMUX_OPENER_SSH_HOST=$(shell_quote "$ssh_host")"
fi
if [ -n "$fallback" ]; then
  picker_cmd="$picker_cmd TMUX_OPENER_FALLBACK=$(shell_quote "$fallback")"
fi
if [ -n "$fallback_command" ]; then
  picker_cmd="$picker_cmd TMUX_OPENER_FALLBACK_COMMAND=$(shell_quote "$fallback_command")"
fi
if [ -n "$bridge_policy" ]; then
  picker_cmd="$picker_cmd TMUX_OPENER_BRIDGE_POLICY=$(shell_quote "$bridge_policy")"
fi
if [ -n "$route_feedback" ]; then
  picker_cmd="$picker_cmd TMUX_OPENER_ROUTE_FEEDBACK=$(shell_quote "$route_feedback")"
fi
picker_cmd="$picker_cmd $(shell_quote "$CURRENT_DIR/scripts/tmux-opener-pick") --capture-pane --target-pane \"\$(tmux display-message -p '#{pane_id}')\""
if [ -n "$picker_history_lines" ]; then
  picker_cmd="$picker_cmd --history-lines $(shell_quote "$picker_history_lines")"
fi
if [ -n "$picker_prompt" ]; then
  picker_cmd="$picker_cmd --prompt $(shell_quote "$picker_prompt")"
fi
if [ -n "$picker_fzf_height" ]; then
  picker_cmd="$picker_cmd --fzf-height $(shell_quote "$picker_fzf_height")"
fi

popup_cmd="$picker_cmd; status=\$?; if [ \$status -eq 0 ] || [ \$status -eq 130 ]; then tmux display-popup -C; else printf '\n tmux-opener exited with status %s. Press Enter to close. ' \"\$status\"; read _; tmux display-popup -C; fi"
tmux bind-key "$picker_key" display-popup -d "#{pane_current_path}" -w 90% -h 70% "$popup_cmd"
