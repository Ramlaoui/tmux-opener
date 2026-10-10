# Local opener bridge uses structured allowlisted requests

Remote tmux sessions send structured Open Requests to the Local Opener Client rather than shell commands. The client accepts only allowlisted actions, restricts URL schemes, and requires explicit SSH host allowlisting for VS Code Remote-SSH path opens because the SSH-forwarded socket is a transport boundary, not a complete authorization model.

Download Requests use the same SSH host allowlist. They contain an absolute
remote path and a boolean asking for a local save dialog. The client chooses the
destination and constructs a fixed, shell-quoted SSH command to read a regular
file. Remote requests cannot specify local destination paths or shell commands.
Downloads are queued asynchronously and published only after SSH succeeds,
without overwriting existing files.
