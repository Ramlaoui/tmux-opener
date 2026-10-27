# Demo host for the documentation recordings

The recordings on the documentation site come from a disposable SSH host
named `devbox`, with its own user (`demo`), tmux server and a made-up project
(`~/vision-lab`). Nothing from a real machine appears on screen.

## Start the host

From the repository root:

```sh
docker build -f demo/Dockerfile -t tmux-opener-demo .
docker run -d --name tmux-opener-demo --hostname devbox -p 127.0.0.1:2222:22 tmux-opener-demo

ssh-keygen -t ed25519 -N '' -f /tmp/demo/id_demo
docker exec -i tmux-opener-demo sh -c 'cat > /etc/ssh/demo_keys/demo' < /tmp/demo/id_demo.pub
```

Point a throwaway SSH config at it:

```sshconfig
Host devbox
  HostName 127.0.0.1
  Port 2222
  User demo
  IdentityFile /tmp/demo/id_demo
  UserKnownHostsFile /tmp/demo/known_hosts
  StrictHostKeyChecking accept-new
```

Then run the desktop client with its own `HOME`, so your own settings,
history and Downloads folder stay out of the recordings, and connect with
`tmux-opener ssh devbox`. Use a separate browser and VS Code profile for the
same reason.

## Play a scene

With a terminal attached to the `lab` session, drive it from outside:

```sh
docker exec -u demo -e USER=demo tmux-opener-demo \
  python3 /home/demo/.tmux/plugins/tmux-opener/demo/scenes.py SCENE
```

`scenes.py` lists the scenes. Keys go through tmux itself, so copy mode and
prefix bindings behave as if typed. Record the screen region around the
terminal while the scene plays.

Before publishing, check every frame: native dialogs can show the Finder
sidebar and recent folders, and notifications can come from other apps.
