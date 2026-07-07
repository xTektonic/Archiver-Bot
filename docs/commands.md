# Commands and Syncing

Command descriptions changed during the rewrite. Approved changes are recorded in `COMMAND_CHANGES.md`.

## Command Sync Options

### `ARCHIVER_SYNC_COMMANDS=true`

Use this when command definitions changed and Discord needs to receive the new slash/context command tree.

Best for:

- first staging boot
- first production boot after rewrite
- intentional command name/description/parameter changes

Tradeoff:

- startup makes a Discord API sync call
- repeated unnecessary syncs add noise and may slow startup

### `ARCHIVER_SYNC_COMMANDS=false`

Use this for normal production restarts after commands are already registered.

Best for:

- routine restarts
- deploys that do not change command definitions
- reducing startup API activity

Tradeoff:

- command changes will not appear until a sync is run later

## Recommendation

For the rewrite rollout:

1. Set `ARCHIVER_SYNC_COMMANDS=true`.
2. Start the bot and confirm commands appear.
3. Stop the bot.
4. Set `ARCHIVER_SYNC_COMMANDS=false`.
5. Restart for normal operation.

## Current Command Surfaces

Slash commands:

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

Context menu commands:

- `Edit`
- `Delete`
- `Publish post`
- `Append post`
- `Pin`

Expected local command count after cogs load: `21`.
