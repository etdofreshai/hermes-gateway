#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Hermes Gateway Entrypoint
#
# 1. Set up SSH authorized_keys from env var (if present)
# 2. Start SSH server in background (for interactive access)
# 3. Run .hermes setup hooks if first boot
# 4. Start Hermes gateway as PID 1 (or foreground process)
# ---------------------------------------------------------------------------

echo "[entrypoint] Hermes Agent Gateway starting..."

# --- SSH setup ---
if [ -n "${SSH_AUTHORIZED_KEYS:-}" ]; then
    mkdir -p /root/.ssh
    echo "$SSH_AUTHORIZED_KEYS" > /root/.ssh/authorized_keys
    chmod 700 /root/.ssh
    chmod 600 /root/.ssh/authorized_keys
    echo "[entrypoint] SSH authorized_keys configured"
fi

# Start sshd in background if the binary exists
if command -v sshd &>/dev/null; then
    /usr/sbin/sshd -D -e &
    SSHD_PID=$!
    echo "[entrypoint] SSH server started (PID $SSHD_PID)"
fi

# --- First-boot check ---
if [ ! -f /root/.hermes/.env ]; then
    echo "[entrypoint] WARNING: No .env file found at /root/.hermes/.env"
    echo "[entrypoint] Mount your config volume or set Dokploy env vars."
fi

if [ ! -f /root/.hermes/config.yaml ]; then
    echo "[entrypoint] WARNING: No config.yaml found at /root/.hermes/config.yaml"
fi

# --- Agent CLI installs (claude, codex, opencode, pi) ---
# These installers land in /root/.local/bin etc., which is volume-mounted,
# so they have to run at runtime — not at image build time.
# Re-run by deleting /root/.hermes/.cli-installed and restarting the container.
mkdir -p /root/.hermes
CLI_MARKER=/root/.hermes/.cli-installed
if [ ! -f "$CLI_MARKER" ]; then
    echo "[entrypoint] First-boot agent CLI install..."
    : > "${CLI_MARKER}.log"

    install_cli() {
        local name=$1 url=$2 sh=$3
        echo "[entrypoint] installing $name from $url"
        if curl -fsSL "$url" | "$sh" >>"${CLI_MARKER}.log" 2>&1; then
            echo "$name ok" >> "$CLI_MARKER"
        else
            echo "[entrypoint] WARN: $name install failed (see ${CLI_MARKER}.log)"
            echo "$name FAILED" >> "$CLI_MARKER"
        fi
    }

    install_cli claude   https://claude.ai/install.sh           bash
    install_cli codex    https://chatgpt.com/codex/install.sh   sh
    install_cli opencode https://opencode.ai/install            bash
    install_cli pi       https://pi.dev/install.sh              sh

    echo "[entrypoint] Agent CLI install complete (marker: $CLI_MARKER)"
else
    echo "[entrypoint] Agent CLIs already installed (marker present)"
fi

# --- Start Hermes Gateway ---
echo "[entrypoint] Starting Hermes gateway..."
echo "[entrypoint] Version: $(hermes --version 2>&1 || echo 'unknown')"

# Use exec so hermes gateway becomes PID 1 (receives signals properly)
exec hermes gateway run
