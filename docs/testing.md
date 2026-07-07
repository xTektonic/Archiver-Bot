# Testing

## Fast Checks

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check src tests main.py
```

Expected current result:

- `pytest`: 6 passing tests
- `ruff`: all checks passing

## Command Loading Smoke Test

This loads cogs and counts registered commands without connecting to Discord:

```powershell
.\.venv\Scripts\python.exe -c "exec('import asyncio\nfrom archiver_bot.app import create_bot\nasync def main():\n    bot = create_bot()\n    await bot.setup_hook()\n    print(len(bot.tree.get_commands()))\n    await bot.close()\nasyncio.run(main())')"
```

Expected current command count:

```text
21
```

## Modal Compatibility Smoke Test

```powershell
.\.venv\Scripts\python.exe -c "exec('import asyncio\nfrom types import SimpleNamespace\nfrom archiver_bot.app import create_bot\nfrom archiver_bot.cogs.archive import PublishModal, AppendModal, SendModal\nasync def main():\n    bot=create_bot()\n    draft=SimpleNamespace(channel=SimpleNamespace(name=\"Draft Title\"), content=\"Body\")\n    PublishModal(bot, draft)\n    AppendModal(bot, draft)\n    SendModal(bot, SimpleNamespace(), True)\n    await bot.close()\n    print(\"modal construction ok\")\nasyncio.run(main())')"
```

## Type Checking

`mypy` is installed but is not currently a release gate. The 1:1 legacy parser and discord.py dynamic types produce substantial noise. Prefer tests, lint, and Discord staging behavior until the legacy parser is intentionally typed or wrapped.

## Staging Discord Checklist

Run these in a test/staging Discord environment before production:

- Bot starts and logs online.
- Commands appear after command sync.
- `/send` sends plain and embed messages.
- Message context `Edit` edits bot messages.
- Message context `Delete` creates an approval request.
- `Publish post` creates an archive thread.
- `Append post` appends to an archive thread.
- `Pin` works only where allowed.
- `/tag_selector` works for staff and help-post owners.
- New submissions create tracker records.
- Tracker summary rebuild works.
- Approval buttons reject self-approval.
- Approval buttons still work after restart.
- DM forwarding works.
- DM block button persists state.
- No-chat moderation deletes, warns, times out, and logs.
- Parser commands write JSON to `ARCHIVER_DATA_DIR/parsed`.
- Maintenance commands work in dry-run before live mode.
