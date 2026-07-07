# Developer Checks

There is no automated test suite at the moment. Use lint and smoke checks before pushing changes.

## Lint

```powershell
.\.venv\Scripts\python.exe -m ruff check src main.py
```

## Command Loader Smoke Check

Loads cogs and counts registered commands without connecting to Discord:

```powershell
.\.venv\Scripts\python.exe -c "exec('import asyncio\nfrom app import create_bot\nasync def main():\n    bot = create_bot()\n    await bot.setup_hook()\n    print(len(bot.tree.get_commands()))\n    await bot.close()\nasyncio.run(main())')"
```

Expected command count: `21`.

## Modal Smoke Check

Constructs the archive modals inside an event loop:

```powershell
.\.venv\Scripts\python.exe -c "exec('import asyncio\nfrom types import SimpleNamespace\nfrom app import create_bot\nfrom cogs.archive import PublishModal, AppendModal, SendModal\nasync def main():\n    bot=create_bot()\n    draft=SimpleNamespace(channel=SimpleNamespace(name=\"Draft Title\"), content=\"Body\")\n    PublishModal(bot, draft)\n    AppendModal(bot, draft)\n    SendModal(bot, SimpleNamespace(), True)\n    await bot.close()\n    print(\"modal construction ok\")\nasyncio.run(main())')"
```

## Live Staging Checklist

- Bot starts and logs online.
- Commands appear after sync.
- `/send` works with plain text and embeds.
- Context commands work: `Edit`, `Delete`, `Publish post`, `Append post`, `Pin`.
- Approval buttons reject self-approval and work after restart.
- Submission tracker creates records and rebuilds summaries.
- DM forwarding and DM blocking work.
- No-chat moderation warns, times out, deletes, and logs.
- Parser commands write files to `ARCHIVER_DATA_DIR/parsed`.
- Maintenance commands are checked in dry-run before live mode.
