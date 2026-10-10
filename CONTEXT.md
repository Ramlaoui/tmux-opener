# tmux-opener

This context defines the language for opening local desktop targets from remote tmux sessions.

## Language

**Local Opener Bridge**:
The client-mediated boundary where a remote terminal session asks a local desktop session to open a target or download a file. It is not remote command execution on the local machine.
_Avoid_: Ghostty bridge, xdg-open forwarding, remote GUI opener

**Remote Opener Plugin**:
The tmux-facing participant that turns selected terminal text into an Open Request or Download Request. It belongs to the remote session and does not own local desktop behavior.
_Avoid_: local opener, desktop plugin

**Local Opener Client**:
The desktop-side participant that receives requests and decides how they are satisfied locally. It owns local browser and editor dispatch, file transfers, and save dialogs.
_Avoid_: remote daemon, tmux daemon

**Open Request**:
A structured statement of intent to open a URL or a remote file path. It is data, not a shell command.
_Avoid_: open command, shell snippet

**Download Request**:
A structured request to copy a remote regular file to the client machine. The
Local Opener Client owns the destination: its Downloads folder, or a location
selected in a local save dialog. An acknowledgement means the transfer was
queued; completion is reported by the client. The client applies the same SSH
host allowlist as remote editor requests and constructs the fixed SSH file-read
command itself.

**Download Queue**:
The Local Opener Client's persistent records and bounded transfer workers. Each
accepted download has an ID, state, byte count, destination, timestamps and
failure detail. A retry creates a new record; unfinished records are interrupted
after restart. The client owns cancellation and publication of complete files.

**Status Snapshot**:
A structured view of the current client, plugin-reported host information and
download records. The host's tmux dashboard reads its forwarded client, while
the local browser dashboard aggregates the desktop's client sockets. A reachable
client process and a recent host report do not prove an active SSH connection.

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
