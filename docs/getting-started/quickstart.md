---
title: Quickstart
description: Connect to a host with the bridge and open your first URL, file and download.
---

# Quickstart

This walk-through assumes you [installed](installation.md) the plugin on a host called `devbox` and the client on your laptop.

## 1. Connect with the bridge

From your laptop:

```sh
tmux-opener ssh devbox
```

The first run:

1. backs up `~/.ssh/config` and adds an `Include` for a managed snippet in `~/.ssh/tmux-opener.d/`,
2. writes `devbox.conf` there with a `RemoteForward` from the host's socket to your laptop,
3. starts a local `tmux-opener-client` for `devbox`,
4. runs `ssh devbox`.

From then on, a plain `ssh devbox` carries the bridge too, including from VS Code or other tools. Want to see the changes first?

```sh
tmux-opener ssh --dry-run --no-start-client devbox
```

!!! note "Set up without connecting"

    `tmux-opener install-host --start-client devbox`, or **Add bridge** in a [dashboard](../guides/dashboards.md#add-a-bridge), writes the snippet and starts the client without opening a session.

## 2. Open something

Start or attach tmux on the host, print a URL and a path, then enter copy mode with <kbd>prefix</kbd> <kbd>[</kbd>:

```sh
echo "https://github.com/Ramlaoui/tmux-opener  src/vision/model.py:24"
```

Select the URL and press <kbd>o</kbd>: it opens in your laptop's browser. Select `src/vision/model.py:24` and press <kbd>o</kbd>: VS Code opens the file on `devbox` at line 24.

Prefer not to select? Press <kbd>prefix</kbd> <kbd>o</kbd> for the [target picker](../guides/picker.md).

## 3. Move files

- Select a path and press <kbd>d</kbd> to download it to your laptop's Downloads folder.
- Press <kbd>D</kbd> instead to choose where to save it.
- Press <kbd>prefix</kbd> <kbd>P</kbd> to pick files on your laptop and upload them into the pane's directory.

Follow transfers with <kbd>prefix</kbd> <kbd>O</kbd>.

## Keys at a glance

| Where | Key | Action |
| --- | --- | --- |
| copy mode | <kbd>o</kbd> | Open the selection on your laptop |
| copy mode | <kbd>i</kbd> | View the selection inline on the host |
| copy mode | <kbd>d</kbd> | Download to Downloads |
| copy mode | <kbd>D</kbd> | Download with a save dialog |
| prefix | <kbd>o</kbd> | Target picker |
| prefix | <kbd>P</kbd> | Upload files into the pane's directory |
| prefix | <kbd>O</kbd> | Dashboard |

All of them can be changed: see [keys and options](../reference/keys-and-options.md).

## If nothing happens

```sh
tmux-opener doctor devbox            # local checks
tmux-opener doctor devbox --remote   # also ping the bridge through SSH
```

See [troubleshooting](../troubleshooting.md) for common causes.
