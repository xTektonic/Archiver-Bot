# Configuration

Configuration is loaded by `config.settings.load_settings`.

## Environment Variables

```text
DISCORD_BOT_TOKEN=required
ARCHIVER_DATA_DIR=optional, defaults to ./data
ARCHIVER_SYNC_COMMANDS=optional, defaults to false
```

## Discord IDs

Guild-specific IDs live in `src/config/settings.py` as typed dataclasses:

- `RoleIds`
- `ChannelIds`
- `TagIds`
- `CategoryIds`
- `CopyText`

The bot is intentionally configured for one Discord guild. If a channel, role, category, or tag changes in Discord, update the matching dataclass value.

## Secrets

Only environment variables should contain secrets. Do not commit `.env`, bot tokens, production data, or generated state.

## Production Defaults

Recommended production environment:

```text
DISCORD_BOT_TOKEN=<real token>
ARCHIVER_DATA_DIR=/var/lib/archiver-bot
ARCHIVER_SYNC_COMMANDS=false
```

Set `ARCHIVER_SYNC_COMMANDS=true` only for intentional command registration updates.
