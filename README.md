# Archiver-Bot

Archiver-Bot is the Discord workflow bot for TMCC, the Technical Minecraft Community Catalogue.

## Run

```bash
python -m pip install -e ".[dev]"
python main.py
```

Set `DISCORD_BOT_TOKEN` before starting the bot. Runtime data is stored in the local `data/` folder.

## Documentation

- [Architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [Runtime State](docs/runtime-state.md)
- [Deployment](docs/deployment.md)
- [Commands](docs/commands.md)
- [Parser](docs/parser.md)
- [Operational Runbook](docs/runbook.md)
