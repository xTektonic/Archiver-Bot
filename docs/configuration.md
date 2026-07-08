# Configuration

Configuration is loaded from environment variables and `src/config/settings.py`.

## Environment

```text
DISCORD_BOT_TOKEN=required
```

## Guild IDs

Edit these dataclasses in `src/config/settings.py` when Discord IDs change:

- `RoleIds`
- `ChannelIds`
- `TagIds`
- `CategoryIds`
- `CopyText`

The bot is built for one guild. Do not add multi-guild abstractions unless the bot actually needs them.

## Runtime Data

Runtime data is stored in the local `data/` folder.
