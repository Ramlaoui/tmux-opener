---
title: Security model
description: What a remote tmux session can and cannot make your laptop do through tmux-opener.
---

# Security model

A bridge from a remote machine into your desktop must be narrow. tmux-opener treats the forwarded socket as a transport, not as proof that a request is safe, and the desktop client decides everything.

## Requests are data, never commands

The host sends small JSON requests: *open this URL*, *open this remote path*, *download this path*, *upload into this directory*. The client accepts a fixed set of actions and builds every command itself, with fixed, quoted arguments. Nothing in a request is run by a shell on your laptop.

| A remote session can… | It cannot… |
| --- | --- |
| open `http`/`https` URLs | launch other URL schemes or local apps |
| open paths on an allowed SSH host in VS Code | open or read files on your laptop |
| ask for a tunnel to a port on that host | forward arbitrary hosts or ports to your laptop |
| ask to download remote files | pick where they land, beyond asking for a save dialog |
| ask you to upload files into a directory | name, list or read local files: you pick them |
| change opener settings to fixed values | store commands in settings |

## Allowlists

- **URL schemes:** `http` and `https` unless you start the client with `--allow-url-scheme`.
- **SSH hosts:** file, folder, tunnel and transfer requests are accepted only for the host the client was started for, or hosts added with `--allow-ssh-host`.
- **Local previews:** only document, image, audio and video formats that cannot run code when opened.

## The socket

The client listens on a Unix socket in `~/.local/state/tmux-opener/` with mode `0600`. SSH forwards it to `/tmp/tmux-opener-$USER.sock` on the host, so anyone who can use that remote socket (you, and root on the host) can send requests while you are connected. Only connect bridges to hosts where that is acceptable.

## Transfers

- Downloads and uploads use your SSH config for the same host alias, with inherited forwards and shared connections disabled, and never prompt for passwords.
- Files are published atomically and never overwrite existing files, on either side.
- Folder downloads refuse archive entries that escape the destination and skip device files and links that leave it.
- Tunnels for `localhost` URLs bind to `127.0.0.1` on your laptop and request only the one forward they need.

## The browser dashboard

`tmux-opener dashboard` listens on a loopback port and requires a random per-run token, so other local users and web pages cannot drive it.

## Logs

Normal logs record actions without request targets. `--verbose` (or `--client-verbose`) logs URLs, query tokens, remote paths and SSH diagnostics: treat those logs as private and redact them before sharing.

## Robustness

Each request is read under a two-second deadline and a 1 MiB limit. Up to 32 connections are admitted, desktop actions run one at a time with one waiting request, and health checks stay responsive while a slow request is handled.

The design decisions behind this are recorded in [ADR 0001](../adr/0001-local-opener-bridge-trust-model.md) and [ADR 0002](../adr/0002-ssh-config-owns-host-socket-wiring.md).
