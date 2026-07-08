# Runbook

## Bot Does Not Start

1. Confirm `DISCORD_BOT_TOKEN`.
2. Confirm dependencies are installed.
3. Confirm `data/` exists or can be created.
4. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m ruff check src main.py
   ```

## Commands Missing

1. Restart the bot.
2. Confirm commands appear.
3. If needed, run `/restart update:true branch:main`.

## State Looks Wrong

1. Stop the bot.
2. Back up `data/state.json`.
3. Check `data/backups/`.
4. Inspect `state.json`.
5. Restore from backup if needed.

## Tracker Summary Is Wrong

1. Run `/tracker_list`.
2. Check `tracked_submissions` in `state.json`.
3. Check tracker channel IDs in `src/config/settings.py`.

## Approval Button Does Nothing

1. Confirm the approval is `pending` in `state.json`.
2. Confirm `expires_at` has not passed.
3. Confirm the approver has a higher role.
4. Restart the bot to restore pending approval views.

## Parser Errors

1. Run `/parse_post` on one post.
2. Read the diagnostic.
3. Fix the archive post format.
4. Re-run parsing.
