# Local opener bridge uses structured allowlisted requests

Remote tmux sessions send structured Open Requests to the Local Opener Client rather than shell commands. The client accepts only allowlisted actions, restricts URL schemes, and requires explicit SSH host allowlisting for VS Code Remote-SSH path opens because the SSH-forwarded socket is a transport boundary, not a complete authorization model.
