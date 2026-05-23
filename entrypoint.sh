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

# --- Start Hermes Gateway ---
echo "[entrypoint] Starting Hermes gateway..."
echo "[entrypoint] Version: $(hermes --version 2>&1 || echo 'unknown')"

# Use exec so hermes gateway becomes PID 1 (receives signals properly)
exec hermes gateway run
