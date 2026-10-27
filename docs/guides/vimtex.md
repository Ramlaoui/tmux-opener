---
title: VimTeX PDF preview
description: Compile LaTeX on the host with VimTeX and get a live-refreshing PDF viewer on your laptop.
---

# VimTeX PDF preview

Write LaTeX in Neovim on the host and read the PDF on your laptop. VimTeX compiles remotely; the client fetches the PDF over SSH, opens it in your local viewer, and refreshes that same viewer after every successful build. You don't need a web server or to copy PDFs by hand.

## Set up

On the host, load the adapter before VimTeX initializes (with lazy.nvim, put it in VimTeX's `init` function):

```lua
dofile(vim.fn.expand('~/.tmux/plugins/tmux-opener/integration/vimtex.lua')).setup()
```

If the plugin lives elsewhere, use that checkout's absolute path. Compile-success refreshes are sent with `uv run --no-project --no-sync`, so the host needs `uv`.

## Use

Connect with `tmux-opener ssh HOST`, open the `.tex` file in remote Neovim and press `\ll`. The first successful build opens the PDF locally; later builds refresh it in place. `\lv` opens it on demand.

The adapter only changes VimTeX when the bridge is reachable and the client advertises PDF support. Without a bridge, or with an older client, your usual VimTeX viewer is left alone.

## Viewers

The default is Zathura on Linux when installed, Skim on macOS when installed, or the system PDF handler. Choose another under `pdf_viewer` on the [Openers page](opener-rules.md#other-settings). Skim reloads the matching document without activating the app; turn off Skim's own "Check for file changes" in its Sync preferences. A failed transfer keeps the previous PDF.
