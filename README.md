# Archiver-Bot

Archiver-Bot is a Discord workflow bot for a single archive guild. It manages archive submissions, approval flows, moderation helpers, archive parsing, and routine forum maintenance.

## Runtime Data

Set `ARCHIVER_DATA_DIR` on production, for example:

```bash
ARCHIVER_DATA_DIR=/var/lib/archiver-bot
```

The bot creates:

- `state.json` for persistent bot state
- `parsed/` for generated archive parser output
- `backups/` for state backups before migrations

These paths are ignored by Git, so `git pull` will not overwrite production state.

## Local Run

```bash
python -m pip install -e ".[dev]"
python main.py
```

Required environment variables:

- `DISCORD_BOT_TOKEN`
- `ARCHIVER_DATA_DIR` optional, defaults to `./data`
- `ARCHIVER_SYNC_COMMANDS` optional, set to `true` to sync slash commands on startup

## AWS Update Checklist

1. Pull the code update.
2. Confirm `ARCHIVER_DATA_DIR` points outside tracked source or to ignored `data/`.
3. Restart the service.
4. Confirm the online log message appears.
5. Run a tracker rebuild.
6. Verify `state.json` still exists after update.

## Documentation

- [Architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [Runtime State](docs/runtime-state.md)
- [Deployment](docs/deployment.md)
- [Developer Checks](docs/testing.md)
- [Commands and Syncing](docs/commands.md)
- [Parser](docs/parser.md)
- [Operational Runbook](docs/runbook.md)
