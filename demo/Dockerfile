# A disposable SSH host for recording the documentation demos. It has its own
# user, hostname, tmux server and made-up project, so nothing from a real
# machine appears on screen. See demo/README.md.
FROM debian:trixie-slim

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      openssh-server tmux git python3 python-is-python3 python3-matplotlib fzf bat chafa poppler-utils jq rsync less \
      curl wget ca-certificates procps file tree \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s /usr/bin/batcat /usr/local/bin/bat \
    && useradd --create-home --shell /bin/bash demo \
    && mkdir -p /run/sshd /etc/ssh/demo_keys

COPY demo/sshd_config /etc/ssh/sshd_config.d/demo.conf
COPY --chown=demo:demo demo/tmux.conf /home/demo/.tmux.conf
COPY --chown=demo:demo demo/bashrc /home/demo/.bashrc_demo
COPY --chown=demo:demo . /home/demo/.tmux/plugins/tmux-opener
COPY --chown=demo:demo demo/project /tmp/project

USER demo
RUN echo '. ~/.bashrc_demo' >> ~/.bashrc \
    && python3 /tmp/project/make-project.py ~/vision-lab \
    && git config --global init.defaultBranch main

USER root
EXPOSE 22
CMD ["/usr/sbin/sshd", "-D", "-e"]
