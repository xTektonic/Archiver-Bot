# Operational Runbook

## Bot Does Not Start

1. Confirm `.env` or service environment contains `DISCORD_BOT_TOKEN`.
2. Confirm dependencies are installed.
3. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest
   .\.venv\Scripts\python.exe -m ruff check src tests main.py
   ```

4. Check whether `ARCHIVER_DATA_DIR` is writable.

## Commands Missing In Discord

1. Set `ARCHIVER_SYNC_COMMANDS=true`.
2. Restart the bot once.
3. Confirm commands appear.
4. Set `ARCHIVER_SYNC_COMMANDS=false`.
5. Restart again.

## State Looks Wrong

1. Stop the bot.
2. Back up `ARCHIVER_DATA_DIR/state.json`.
3. Check `ARCHIVER_DATA_DIR/backups/`.
4. Inspect `state.json` for malformed IDs or statuses.
5. Restore from backup if needed.

## Tracker Summary Is Wrong

1. Run `/tracker_list`.
2. Confirm tracked submissions exist in `state.json`.
3. Confirm tracker channel IDs in settings still match Discord.
4. If a Discord message was manually deleted, rebuild the summary.

## Approval Button Does Nothing

1. Confirm the approval is still `pending` in `state.json`.
2. Confirm `expires_at` has not passed.
3. Confirm the approver has a higher role.
4. Restart the bot to restore pending approval views.

## Parser Errors

1. Parse a single post first with `/parse_post`.
2. Read the diagnostic message.
3. Fix the archive post format.
4. Re-run parsing.

## Before Manual Destructive Actions

Use dry-run options where available:

- `/close_resolved dry_run:true`
- `/open_archived dry_run:true`

Only run live mode after reviewing the dry-run count.
