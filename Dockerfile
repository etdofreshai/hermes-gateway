# Hermes Agent Gateway — Dockerfile for Dokploy deployment
# Builds a self-contained image that runs `hermes gateway run` as PID 1.

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV HERMES_HOME=/root/.hermes
ENV PATH="/root/.local/bin:/root/.opencode/bin:/root/.pi/bin:/usr/local/lib/hermes-agent/venv/bin:/usr/local/bin:/usr/bin:/bin"

# ---------------------------------------------------------------------------
# 1. System dependencies
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        git \
        openssh-server \
        python3-dev \
        python3-pip \
        python3-venv \
        ripgrep \
        rsync \
        sudo \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# 2. Node.js (for MCP servers like Context7, Claude Code, etc.)
# ---------------------------------------------------------------------------
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*
# npm ships with nodejs; skip self-upgrade (nodesource bundle can be incomplete)

# ---------------------------------------------------------------------------
# 3. Hermes Agent
# ---------------------------------------------------------------------------
# Primary: curl installer (tracks main, installs with --extra all so telegram,
# slack, etc. are present). Falls back to PyPI with [all] extras if curl path
# fails. --skip-setup avoids the interactive post-install wizard; --skip-browser
# skips playwright/chromium since this image is headless.
RUN curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh \
        | bash -s -- --skip-setup --skip-browser \
    || pip3 install --break-system-packages 'hermes-agent[all]'

# Ensure the CLI is on PATH
RUN ln -sf /usr/local/lib/hermes-agent/venv/bin/hermes /root/.local/bin/hermes 2>/dev/null || true
RUN hermes --version

# ---------------------------------------------------------------------------
# 4. Agent CLIs (Claude Code, Codex, opencode, pi) — installed on first boot
#    via entrypoint.sh, since they land in /root which is volume-mounted.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 5. SSH server setup (so you can still SSH into the container)
# ---------------------------------------------------------------------------
RUN mkdir -p /run/sshd
# SSH_AUTHORIZED_KEYS env var is set via Dokploy; entrypoint writes it.

# ---------------------------------------------------------------------------
# 6. Runtime directories
# ---------------------------------------------------------------------------
RUN mkdir -p /root/.hermes/logs /root/.hermes/sessions /root/.hermes/memories \
    /root/.hermes/skills /root/.hermes/sounds /root/workspace

# ---------------------------------------------------------------------------
# 7. Entrypoint
# ---------------------------------------------------------------------------
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
