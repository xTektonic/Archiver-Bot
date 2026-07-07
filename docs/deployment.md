# Deployment

## Install

From the repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .[dev]
```

On Linux/AWS, the same flow is:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

Production can install without dev extras:

```bash
.venv/bin/python -m pip install -e .
```

## Environment

Create `.env` or configure the service manager:

```text
DISCORD_BOT_TOKEN=<token>
ARCHIVER_DATA_DIR=/var/lib/archiver-bot
ARCHIVER_SYNC_COMMANDS=false
```

## First Rewrite Deployment

1. Stop the current bot.
2. Back up old runtime files: `blacklist.json`, `messages.json`, `accepted.json`.
3. Pull the rewrite branch.
4. Install dependencies.
5. Place old runtime files in the working directory if importing them on first boot.
6. Set `ARCHIVER_SYNC_COMMANDS=true` for the first boot if command registration needs updating.
7. Start the bot.
8. Confirm `ARCHIVER_DATA_DIR/state.json` was created.
9. Set `ARCHIVER_SYNC_COMMANDS=false` for normal restarts.

## Update Deployment

1. Stop the service.
2. Pull code.
3. Reinstall dependencies if `pyproject.toml` changed.
4. Start the service.
5. Confirm the bot logs online.
6. Confirm `state.json` still exists and was not overwritten.

## Production Service Notes

- Run only one bot process at a time.
- Keep `ARCHIVER_DATA_DIR` outside the repo when practical.
- Do not run production with `ARCHIVER_SYNC_COMMANDS=true` permanently.
- Keep `.venv/`, `data/`, and `.env` out of Git.
