# Architecture

Archiver-Bot is now a `src/` layout Python project. Runtime code lives in `src`, tests live in `tests`, and mutable runtime data is kept outside Git under `ARCHIVER_DATA_DIR`.

## Package Layout

```text
src/
  app.py              Bot factory, service wiring, extension loading
  cogs/               Discord command and event surfaces
  config/             Typed settings and guild IDs
  models/             Runtime state and parser data shapes
  parser/             Archive post parser implementation
  services/           Business logic behind commands/events
  storage/            Local file persistence
  jobs/               Maintenance job namespace
```

## Design Rules

- Cogs should stay thin. They translate Discord interactions into service calls.
- Services own behavior. Tracker, approvals, moderation, archive publishing, parsing, and maintenance each have a service.
- State writes go through `StateStore`; commands and events should not open JSON files directly.
- Discord sends default to no mentions unless a workflow intentionally pings someone.
- Runtime data belongs in `ARCHIVER_DATA_DIR`, not tracked source files.

## Startup Flow

1. `main.py` calls `app.run_bot`.
2. `create_bot()` loads settings and creates service instances.
3. `setup_hook()` initializes state storage and loads all cogs.
4. If `ARCHIVER_SYNC_COMMANDS=true`, slash/context commands are synced.
5. The bot starts with `DISCORD_BOT_TOKEN`.

## Service Responsibilities

- `AuditLogService`: sends structured log embeds.
- `StateService`: safe reads/writes for persistent state.
- `SubmissionTrackerService`: tracks submission posts and tracker summaries.
- `ApprovalService`: persistent approval records and approval buttons.
- `ModerationService`: DM forwarding and no-chat handling.
- `ArchivePublishingService`: publish, append, and role grant workflows.
- `ParserService`: Discord thread collection and parser output writing.
- `MaintenanceJobService`: close/open/lock/inactive scheduled jobs.

## Why This Shape

The original bot stored state in root JSON files and mixed Discord UI, state mutation, and business rules inside large cogs. The rewrite isolates those concerns so workflows can be tested and changed without chasing side effects across unrelated modules.
