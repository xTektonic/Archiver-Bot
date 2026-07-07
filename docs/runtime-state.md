# Runtime State

Runtime state is stored in local JSON files through `StateStore`.

## Directory Layout

```text
ARCHIVER_DATA_DIR/
  state.json
  parsed/
  backups/
```

Default local path:

```text
./data
```

The repository ignores `data/`, so Git updates should not overwrite runtime state.

## State Shape

```json
{
  "version": 1,
  "blocked_dm_users": [],
  "tracker_summary_message_ids": [],
  "accepted_submission_entries": [],
  "last_archive_thread_id": null,
  "tracked_submissions": {},
  "pending_approvals": {},
  "command_change_log": []
}
```

## Write Safety

`StateStore` uses:

- one in-process async lock
- validation before save
- temp-file write
- atomic replace
- backup support before migrations

This is enough for a single bot process on one AWS server. Do not run multiple bot processes against the same state file.

## Legacy Import

On first initialization, if `state.json` does not exist, `StateStore` tries to import:

- `blacklist.json`
- `messages.json`
- `accepted.json`

For production migration, preserve the live copies of those files before deploying the rewrite. If needed, place them in the working directory for the first boot so they can be imported into `state.json`.

## Backups

Backups are written to:

```text
ARCHIVER_DATA_DIR/backups/
```

Before changing the state schema in the future, add migration logic and create a backup first.
