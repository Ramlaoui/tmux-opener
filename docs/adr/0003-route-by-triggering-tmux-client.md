# Route opens by the tmux client that pressed the key

One tmux server can have clients attached over SSH and from the host's own desktop at the same time, while the forwarded socket stays live for as long as any SSH session holds it. The pane, the server environment and the socket all say nothing about who pressed the key, so bindings pass `#{client_pid}` and the Remote Opener Plugin inspects that process.

A client is a Desktop Client only on positive evidence: a local `WAYLAND_DISPLAY` or `:N` `DISPLAY`, no `SSH_CONNECTION`, and no `sshd` in its ancestry. Desktop Clients open with the same-host opener using their own display variables, because the server may have been started over SSH or hold another client's display. Every uncertain case, such as mosh, Tailscale SSH or a host without `/proc`, keeps the bridge path, so a wrong guess can only reproduce the previous behavior.

The bridge cannot be matched to a specific SSH connection: sshd processes are not dumpable, so their sockets and environments are unreadable to the user. With several desktops connected, the most recent forward still receives bridged requests.
