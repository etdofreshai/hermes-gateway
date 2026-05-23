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
