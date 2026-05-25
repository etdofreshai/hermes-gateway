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

# Start sshd in background if the binary exists. openssh-server installs it
# under /usr/sbin, which is not always on PATH in minimal/container envs.
SSHD_BIN="${SSHD_BIN:-/usr/sbin/sshd}"
if [ -x "$SSHD_BIN" ] || SSHD_BIN="$(command -v sshd 2>/dev/null)"; then
    mkdir -p /run/sshd
    "$SSHD_BIN" -D -e &
    SSHD_PID=$!
    echo "[entrypoint] SSH server started (PID $SSHD_PID)"
else
    echo "[entrypoint] WARN: sshd not found; SSH access disabled"
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

    # pi: skip the fancy pi.dev installer (TTY-fussy) and install via npm
    # directly — it's just a globally-installed npm package.
    echo "[entrypoint] installing pi via npm"
    if npm install -g @earendil-works/pi-coding-agent >>"${CLI_MARKER}.log" 2>&1; then
        echo "pi ok" >> "$CLI_MARKER"
    else
        echo "[entrypoint] WARN: pi install failed (see ${CLI_MARKER}.log)"
        echo "pi FAILED" >> "$CLI_MARKER"
        echo "[entrypoint] Retrying pi with --ignore-scripts..."
        if npm install -g --ignore-scripts @earendil-works/pi-coding-agent >>"${CLI_MARKER}.log" 2>&1; then
            # Overwrite FAILED with ok
            sed -i 's/pi FAILED/pi ok/' "$CLI_MARKER"
            echo "[entrypoint] pi installed (with --ignore-scripts)"
        else
            echo "[entrypoint] WARN: pi install also failed with --ignore-scripts"
        fi
    fi

    echo "[entrypoint] Agent CLI install complete (marker: $CLI_MARKER)"
else
    echo "[entrypoint] Agent CLIs already installed (marker present)"
fi

# --- Validate agent CLIs (presence + likely install dir) ---
echo "[entrypoint] Validating agent CLIs..."
for cli in claude codex opencode pi; do
    if path=$(command -v "$cli" 2>/dev/null); then
        echo "[entrypoint]   $cli: $path"
    else
        found=""
        for dir in /root/.local/bin /root/.codex/bin /root/.opencode/bin /root/.pi/bin /root/.bun/bin /usr/local/bin; do
            if [ -x "$dir/$cli" ]; then
                found="$dir/$cli"
                break
            fi
        done
        if [ -n "$found" ]; then
            echo "[entrypoint]   $cli: $found (NOT on PATH)"
        else
            echo "[entrypoint]   $cli: NOT FOUND"
        fi
    fi
done

# --- Hermes install/update on every boot ---
# Image baked in a version at build time, but main moves fast. Try `hermes
# update` first (cheap no-op if current); if hermes isn't on PATH at all, run
# the full installer. Both are non-fatal — gateway still starts on failure.
if command -v hermes >/dev/null 2>&1; then
    echo "[entrypoint] Running 'hermes update'..."
    hermes update || echo "[entrypoint] WARN: hermes update failed (continuing)"
else
    echo "[entrypoint] hermes not on PATH; running installer..."
    curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh \
        | bash -s -- --skip-setup --skip-browser \
        || echo "[entrypoint] WARN: hermes install failed (continuing)"
fi

# --- Apply runtime patches ---
# Patches are baked into the image at /patches/ and applied AFTER hermes update
# so they survive agent upgrades. See apply-patches.sh for details.
if [ -x /apply-patches.sh ]; then
    /apply-patches.sh
fi

# --- Browser + VNC setup (optional remote desktop) ---
# Set BROWSER_ENABLED=1 to start Xvfb, Chrome (CDP), x11vnc, and noVNC
# alongside the gateway. Access via SSH tunnel:
#   ssh -L 6080:127.0.0.1:6080 -L 9222:127.0.0.1:9222 <host>
#   open http://127.0.0.1:6080/vnc.html?autoconnect=1&resize=scale
BROWSER_ENABLED="${BROWSER_ENABLED:-}"
if [ "$BROWSER_ENABLED" = "true" ] || [ "$BROWSER_ENABLED" = "1" ]; then
    echo "[entrypoint] Starting browser + VNC stack..."

    DISPLAY_NUM="${BROWSER_DISPLAY:-99}"
    DISPLAY_VAL=":${DISPLAY_NUM}"
    BROWSER_LOG="/root/.hermes/logs/remote-browser"
    BROWSER_RUN="/root/.hermes/run/remote-browser"
    CDP_PORT="${CHROME_CDP_PORT:-9222}"
    VNC_PORT="${BROWSER_VNC_PORT:-5900}"
    NOVNC_PORT="${BROWSER_NOVNC_PORT:-6080}"
    CHROME_WIDTH="${BROWSER_WIDTH:-1280}"
    CHROME_HEIGHT="${BROWSER_HEIGHT:-900}"
    CHROME_HEADLESS="${CHROME_HEADLESS:-new}"

    mkdir -p "$BROWSER_LOG" "$BROWSER_RUN" "${CHROME_USER_DATA:-/root/.chrome-cdp}"

    # Clean stale display lock
    if [ -e "/tmp/.X${DISPLAY_NUM}-lock" ] && ! pgrep -f "Xvfb ${DISPLAY_VAL}" >/dev/null; then
        rm -f "/tmp/.X${DISPLAY_NUM}-lock"
    fi

    # Xvfb
    if ! pgrep -f "Xvfb ${DISPLAY_VAL}" >/dev/null; then
        Xvfb "$DISPLAY_VAL" -screen 0 "${CHROME_WIDTH}x${CHROME_HEIGHT}x24" -nolisten tcp \
            >"$BROWSER_LOG/xvfb.log" 2>&1 &
        echo $! > "$BROWSER_RUN/xvfb.pid"
        echo "[entrypoint]   Xvfb started on $DISPLAY_VAL (${CHROME_WIDTH}x${CHROME_HEIGHT})"
    fi
    sleep 1

    # Openbox window manager
    DISPLAY="$DISPLAY_VAL" openbox >"$BROWSER_LOG/openbox.log" 2>&1 &
    echo $! > "$BROWSER_RUN/openbox.pid"
    sleep 1

    # Chrome with CDP
    DISPLAY="$DISPLAY_VAL" /root/bin/chrome-cdp about:blank \
        >"$BROWSER_LOG/chrome.log" 2>&1 &
    echo $! > "$BROWSER_RUN/chrome.pid"
    echo "[entrypoint]   Chrome started (CDP port $CDP_PORT)"
    sleep 2

    # Verify CDP
    if curl -fsS --max-time 5 "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1; then
        echo "[entrypoint]   CDP verified on port $CDP_PORT"
    else
        echo "[entrypoint]   WARN: CDP not responding on port $CDP_PORT (may need a moment)"
    fi

    # x11vnc (localhost only, no password — rely on SSH tunnel for auth)
    x11vnc -display "$DISPLAY_VAL" -localhost -forever -shared \
        -rfbport "$VNC_PORT" -nopw >"$BROWSER_LOG/x11vnc.log" 2>&1 &
    echo $! > "$BROWSER_RUN/x11vnc.pid"
    echo "[entrypoint]   x11vnc started on port $VNC_PORT (localhost only)"
    sleep 1

    # noVNC / websockify (localhost only)
    websockify --web="/usr/share/novnc/" "127.0.0.1:${NOVNC_PORT}" "127.0.0.1:${VNC_PORT}" \
        >"$BROWSER_LOG/websockify.log" 2>&1 &
    echo $! > "$BROWSER_RUN/websockify.pid"
    echo "[entrypoint]   noVNC started on port $NOVNC_PORT (localhost only)"
    echo "[entrypoint] Browser + VNC stack ready."
    echo "[entrypoint]   Connect: ssh -L ${NOVNC_PORT}:127.0.0.1:${NOVNC_PORT} -L ${CDP_PORT}:127.0.0.1:${CDP_PORT} <host>"
    echo "[entrypoint]   Open:    http://127.0.0.1:${NOVNC_PORT}/vnc.html?autoconnect=1&resize=scale"
else
    echo "[entrypoint] Browser + VNC disabled (set BROWSER_ENABLED=1 to enable)"
fi

# --- Browser tool CDP config ---
# When browser is disabled, clear the browser.cdp_url in config so the browser
# tool does not spam "Failed to resolve CDP endpoint" warnings on startup.
if [ "$BROWSER_ENABLED" != "true" ] && [ "$BROWSER_ENABLED" != "1" ]; then
    if [ -f /root/.hermes/config.yaml ]; then
        if grep -q 'cdp_url:' /root/.hermes/config.yaml; then
            sed -i 's/^\(\s*cdp_url:\s*\).*/\1/' /root/.hermes/config.yaml
            echo "[entrypoint] Cleared browser.cdp_url (browser disabled)"
        fi
    fi
fi

# --- Start Hermes Gateway ---
echo "[entrypoint] Starting Hermes gateway..."
echo "[entrypoint] Version: $(hermes --version 2>&1 || echo 'unknown')"

# Use exec so hermes gateway becomes PID 1 (receives signals properly)
exec hermes gateway run
