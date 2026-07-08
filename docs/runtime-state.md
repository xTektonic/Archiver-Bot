# Runtime State

Runtime state is local JSON managed by `src/storage/state_store.py`.

## Files

```text
data/
  state.json
  parsed/
  backups/
```

`data/` is ignored by Git and should live in the base Archiver-Bot folder.

## State Contents

`state.json` stores:

- blocked DM user IDs
- tracker summary message IDs
- accepted submission entries
- last archive thread ID
- tracked submissions
- pending approvals

## Write Behavior

`StateStore`:

- serializes writes with an async lock
- validates state by round-tripping through `BotState`
- writes to a temp file
- atomically replaces `state.json`
- creates `parsed/` and `backups/`

Run only one bot process against the data directory.

## Import Files

If `state.json` does not exist, startup can import:

- `blacklist.json`
- `messages.json`
- `accepted.json`

Use this only for bootstrapping existing production state. After a successful import, the legacy JSON files are removed so they are not imported again. Submission tracker rebuilds can also import missing active tracker posts from the tracker channel itself.
