# hermes-gateway

Docker image for running [Hermes Agent](https://github.com/NousResearch/hermes-agent) gateway as a proper containerized service.

## What it does

- Installs Hermes Agent + dependencies (Node.js, Python, ripgrep, etc.)
- Sets up SSH server for interactive access
- Runs `hermes gateway run` as PID 1 via entrypoint
- Mounts persistent volume at `/root/.hermes` for config, sessions, memory, skills
- Mounts workspace at `/root/workspace`

## Dokploy deployment

### Image build

This repo is designed to be deployed as a Dokploy **Application** with:

- **Source:** Docker image built from this repo (or the Dockerfile directly)
- **Command:** `/entrypoint.sh` (set in Dockerfile, override not needed)
- **Volume mount:** `hermes-agent-volume` → `/root` (preserves all state)
- **Port:** `22` (SSH access)

### Environment variables

All secrets should be set in the Dokploy **Environment** section. The key ones:

```
# Required
TELEGRAM_BOT_TOKEN=...
OPENAI_API_KEY=...
OPENROUTER_API_KEY=...

# SSH access
SSH_AUTHORIZED_KEYS=ssh-rsa AAAA... user@host

# Optional providers
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
DEEPSEEK_API_KEY=...
FAL_API_KEY=...

# Optional services
STT_OPENAI_BASE_URL=...
VOICE_TOOLS_OPENAI_KEY=...

# Browser + VNC (optional remote desktop + headless Chrome)
BROWSER_ENABLED=1
CHROME_CDP_PORT=9222
BROWSER_NOVNC_PORT=6080
BROWSER_WIDTH=1280
BROWSER_HEIGHT=900
```

### Volume structure

The persistent volume at `/root/.hermes` contains:

```
/root/.hermes/
├── .env              ← API keys and secrets
├── config.yaml       ← Hermes configuration
├── memories/         ← Persistent memory files
├── sessions/         ← Session transcripts
├── skills/           ← Installed skills
├── state.db          ← Session SQLite database
└── logs/             ← Gateway and error logs
```

### Notes

- **Gateway restart:** The gateway auto-restarts because it's PID 1. If it crashes, Docker restarts the container (set restart policy to `always` or `unless-stopped`).
- **Config changes:** Edit `/root/.hermes/config.yaml` via SSH, then `kill -TERM 1` to restart the gateway cleanly.
- **Domain:** The domain (e.g. `hermes.etdofresh.com`) can point to port `9119` for the dashboard, but the gateway itself only needs outbound internet for Telegram polling.
- **Browser CDP spam:** When `BROWSER_ENABLED` is not set, the entrypoint clears `browser.cdp_url` in config to suppress "Failed to resolve CDP endpoint" warnings. If you enable the browser, the CDP URL is left intact.
- **Agent CLIs:** Claude Code, Codex, opencode, and pi are installed on first boot (not at image build time) since `/root` is volume-mounted. Re-run by deleting `/root/.hermes/.cli-installed` and restarting.
- **pi CLI:** If the npm install fails (native deps), the entrypoint retries with `--ignore-scripts` as a fallback.

## Runtime patches

The `patches/` directory contains Python scripts that modify the Hermes agent source at boot, **after** `hermes update` runs. This lets us customize behavior without losing changes on agent upgrades.

Each patch is a numbered `.py` script that:
1. Reads the target file from the Hermes source
2. Finds unique anchor strings
3. Applies in-place text modifications
4. Is idempotent (safe to re-run)

Current patches:

| Patch | Description |
|-------|-------------|
| `01-telegram-voice-echo.py` | Sends an immediate 🎤 transcript bubble to Telegram when a voice message is transcribed, before the agent processes it |
| `02-telegram-auto-group-photo.py` | Registers Telegram status-update handling and auto-runs `telegram-group-icon` when Hermes is added to a group or included during group creation |

To add a new patch: create `patches/NN-description.py` that accepts the Hermes source dir as `sys.argv[1]` and modifies files in place. The `apply-patches.sh` script runs all `*.py` files from `/patches/` alphabetically.
