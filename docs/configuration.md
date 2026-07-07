# Configuration

Configuration is loaded from environment variables and `src/config/settings.py`.

## Environment

```text
DISCORD_BOT_TOKEN=required
ARCHIVER_DATA_DIR=optional, defaults to ./data
ARCHIVER_SYNC_COMMANDS=optional, defaults to false
```

## Guild IDs

Edit these dataclasses in `src/config/settings.py` when Discord IDs change:

- `RoleIds`
- `ChannelIds`
- `TagIds`
- `CategoryIds`
- `CopyText`

The bot is built for one guild. Do not add multi-guild abstractions unless the bot actually needs them.

## Production Defaults

```text
ARCHIVER_DATA_DIR=/var/lib/archiver-bot
ARCHIVER_SYNC_COMMANDS=false
```

Set `ARCHIVER_SYNC_COMMANDS=true` only while intentionally updating Discord commands.
