# tmux-opener

This context defines the language for opening local desktop targets from remote tmux sessions.

## Language

**Local Opener Bridge**:
The client-mediated boundary where a remote terminal session asks a local desktop session to open a target. It is not remote command execution on the local machine.
_Avoid_: Ghostty bridge, xdg-open forwarding, remote GUI opener

**Remote Opener Plugin**:
The tmux-facing participant that turns selected terminal text into an open request. It belongs to the remote session and does not own local desktop behavior.
_Avoid_: local opener, desktop plugin

**Local Opener Client**:
The desktop-side participant that receives open requests and decides how they are satisfied locally. It owns local browser and editor dispatch.
_Avoid_: remote daemon, tmux daemon

**Open Request**:
A structured statement of intent to open a URL or a remote file path. It is data, not a shell command.
_Avoid_: open command, shell snippet

**Bridge Availability**:
The runtime condition that an Open Request can cross the Local Opener Bridge for the current terminal session.
_Avoid_: SSH detection, remote hostname detection, tmux environment detection

**Bridge Policy**:
The user-selected rule that decides whether Bridge Availability should be used for a given opener action.
_Avoid_: automatic SSH guessing, hostname guessing

**Target Picker**:
The tmux-facing workflow that scans visible terminal text for possible opener targets and asks the user to choose one.
_Avoid_: command launcher, fuzzy opener

## Example Dialogue

Dev: Should the remote tmux plugin call `xdg-open`?
Domain expert: No. The remote plugin emits an Open Request; the Local Opener Client performs local desktop dispatch.

Dev: Is this Ghostty-specific?
Domain expert: No. Ghostty can display fallback terminal hyperlinks, but the Local Opener Bridge is an SSH-forwarded client protocol.

Dev: Should the Remote Opener Plugin decide behavior by detecting whether the pane is SSH?
Domain expert: No. It chooses bridge behavior from Bridge Availability, not from shell or hostname guesses.

Dev: Should a visible-pane picker send shell commands to the local desktop?
Domain expert: No. The Target Picker chooses text, then the Remote Opener Plugin turns that text into an Open Request.
