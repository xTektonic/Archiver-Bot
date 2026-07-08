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
```

## Deploy Steps

1. Stop the bot.
2. Pull the target branch.
3. Reinstall dependencies if `pyproject.toml` changed.
4. Confirm `data/` exists or can be created.
5. Start the bot.
6. Confirm the online log appears.

## Production Notes

- Run one process at a time.
- Back up `data/` before major deployments.
