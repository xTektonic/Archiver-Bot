# Deployment

## Install

Development:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .[dev]
```

Production:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

## Environment

```text
DISCORD_BOT_TOKEN=<token>
ARCHIVER_DATA_DIR=/var/lib/archiver-bot
ARCHIVER_SYNC_COMMANDS=false
```

## Deploy Steps

1. Stop the bot.
2. Pull the target branch.
3. Reinstall dependencies if `pyproject.toml` changed.
4. Confirm `ARCHIVER_DATA_DIR` exists and is writable.
5. Start once with `ARCHIVER_SYNC_COMMANDS=true` if command definitions changed.
6. Set `ARCHIVER_SYNC_COMMANDS=false` for normal restarts.
7. Confirm the online log appears.

## Production Notes

- Run one process at a time.
- Keep runtime state outside the repo.
- Back up `ARCHIVER_DATA_DIR` before major deployments.
