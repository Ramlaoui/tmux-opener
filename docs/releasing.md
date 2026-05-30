# Releasing

## Version tags

A tmux-opener version is released from one shared Git tag:

```sh
git tag v0.1.0
git push origin v0.1.0
```

The `Release` workflow runs shellcheck and the pytest suite through
`uv run --frozen --group dev pytest`, builds both release archives, creates the
GitHub release if needed, and uploads both tarballs plus checksums to the same
release.

## Server-side tmux plugin

The server-side release artifact is a small tarball for remote hosts. It
contains only:

- `tmux-opener.tmux`
- `scripts/tmux-opener-dispatch`
- `scripts/tmux-opener-pick`
- `scripts/tmux-opener-send`
- `scripts/tmux_opener_common.py`
- a server-artifact `README.md`

It deliberately excludes `bin/tmux-opener` and `bin/tmux-opener-client`, which
belong to the local desktop side.

Build the artifact locally:

```sh
scripts/package-server-plugin v0.1.0
```

This writes:

```text
dist/tmux-opener-server-v0.1.0.tar.gz
dist/tmux-opener-server-v0.1.0.tar.gz.sha256
```

## Client-side desktop tools

The client-side release artifact is a small tarball for the local desktop
machine. It contains only:

- `bin/tmux-opener`
- `bin/tmux-opener-client`
- a client-artifact `README.md`

It deliberately excludes the Remote Opener Plugin.

Build the artifact locally:

```sh
scripts/package-client v0.1.0
```

This writes:

```text
dist/tmux-opener-client-v0.1.0.tar.gz
dist/tmux-opener-client-v0.1.0.tar.gz.sha256
```
