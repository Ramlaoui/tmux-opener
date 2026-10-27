---
title: Target picker
description: Choose any URL or path visible in the pane with fzf, without entering copy mode.
---

# Target picker

Press <kbd>prefix</kbd> <kbd>o</kbd> to open a popup listing every URL and path in the visible pane. Type to filter, press <kbd>Enter</kbd>, and the target opens exactly as if you had selected it and pressed <kbd>o</kbd>.

<video class="demo" autoplay loop muted playsinline preload="metadata" poster="../../assets/media/picker.webp" aria-label="The fzf target picker lists URLs and paths from the pane"><source src="../assets/media/picker.mp4" type="video/mp4"></video>

The picker needs `fzf` on the host. It only chooses text: the choice then goes through the same [Open Request](open.md) path, with the same client checks.

## Options

```tmux
set -g @tmux_opener_picker_key 'o'              # prefix key
set -g @tmux_opener_picker_history_lines '200'  # also scan scrollback (default: visible pane only)
set -g @tmux_opener_picker_prompt 'open> '      # fzf prompt
set -g @tmux_opener_picker_fzf_height '40%'     # fzf --height
```
