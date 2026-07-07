# Commands

## Syncing

`ARCHIVER_SYNC_COMMANDS=true` tells the bot to sync slash and context commands during startup.

Use `true` when:

- command names changed
- command descriptions changed
- parameters changed
- deploying to a new bot application

Use `false` for normal restarts.

Recommended flow after command changes:

1. Set `ARCHIVER_SYNC_COMMANDS=true`.
2. Start the bot.
3. Confirm commands appear in Discord.
4. Stop the bot.
5. Set `ARCHIVER_SYNC_COMMANDS=false`.
6. Start the bot normally.

## Slash Commands

- `/guild_list`
- `/leave`
- `/restart`
- `/fetch_links`
- `/tracker_list`
- `/track`
- `/send`
- `/delete_post`
- `/edit_post_title`
- `/grant_role`
- `/close_resolved`
- `/open_archived`
- `/tag_selector`
- `/parse_post`
- `/parse_channel`
- `/parse_archive`

## Context Commands

- `Edit`
- `Delete`
- `Publish post`
- `Append post`
- `Pin`
