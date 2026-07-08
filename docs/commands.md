# Commands

Archiver-Bot syncs commands on startup. `/restart` also has a `sync_commands` option for syncing immediately before a restart.

## Slash Commands

- `/guild_list`  
  Lists the first 10 guilds the bot is in. Moderator only. No parameters.

- `/leave server_id`  
  Makes the bot leave a guild by ID. Moderator only.  
  `server_id`: Discord guild ID.

- `/restart sync_commands`  
  Restarts the bot process. Moderator only.  
  `sync_commands`: if true, syncs Discord commands before restarting.

- `/fetch_links message_id`  
  Returns attachment URLs from a message in the current channel. Archiver/moderator only.  
  `message_id`: Discord message ID to inspect.

- `/servers`  
  Sends the list of other archive servers to the current channel. Moderator only. No parameters.

- `/help`  
  Sends the Archiver Bot command list. Staff only. No parameters.

- `/tracker_list`  
  Rebuilds the submission tracker summary from stored state. Archiver/moderator only.

- `/track`  
  Adds the current submission thread to the tracker. Archiver/moderator only.

- `/send has_embed`  
  Opens a modal to send a bot-authored message in the current channel. Archiver/moderator only.  
  `has_embed`: if true, the modal includes embed fields.

- `/delete_post thread`  
  Requests approval to delete an archive thread. Archiver/moderator only.  
  `thread`: archive thread to delete.

- `/edit_post_title thread`  
  Opens a modal to request an archive thread title change. Archiver/moderator only.  
  `thread`: archive thread to rename.

- `/grant_role member role`  
  Grants either Archived Designer or Submitter. Archiver/moderator only.  
  `member`: member receiving the role.  
  `role`: `Archived Designer` or `Submitter`.

- `/close_resolved dry_run`  
  Closes solved/rejected/archived/inactive/off-topic posts. Archiver/moderator only.  
  `dry_run`: defaults true; reports count without editing when true.

- `/open_archived dry_run`  
  Opens archived archive posts. Archiver/moderator only.  
  `dry_run`: defaults true; reports count without editing when true.

- `/tag_selector given_tag`  
  Sets forum tags for the current post. Staff can use it broadly; help post owners can use it in help posts.  
  `given_tag`: optional tag name. If omitted, shows a tag selector.

- `/parse_post thread`  
  Parses one archive thread and writes JSON output. Archiver/moderator only.  
  `thread`: archive thread to parse.

- `/parse_channel channel`  
  Parses every post in one archive forum. Archiver/moderator only.  
  `channel`: archive forum channel to parse.

- `/parse_archive`  
  Parses all configured archive forums. Archiver/moderator only. No parameters.

## Context Commands

- `Edit`  
  Opens a modal to edit a bot-authored message.

- `Delete`  
  Requests approval to delete a bot-authored message.

- `Publish post`  
  Opens a modal to publish the selected message as a new archive post.

- `Append post`  
  Opens a modal to append the selected message to an existing archive post.

- `Pin`  
  Pins a message in an allowed forum thread when used by the thread owner.
