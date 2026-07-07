# Parser

The parser was ported as close to 1:1 as possible from the original root `parser.py`.

## Files

- `src/archiver_bot/parser/legacy.py`: full legacy parser port
- `src/archiver_bot/models/message.py`: parser output TypedDicts
- `src/archiver_bot/parser/core.py`: small shared helpers such as `slugify`
- `src/archiver_bot/services/parser_service.py`: Discord thread collection and output writing

## Behavior

`ParserService` collects default Discord messages from a thread, builds a per-parse mention username lookup, calls `message_parse`, and writes one JSON file per parsed thread.

Output path:

```text
ARCHIVER_DATA_DIR/parsed/<thread_id>.json
```

## Supported Commands

- `/parse_post`
- `/parse_channel`
- `/parse_archive`

## Important Notes

- The parser remains strict. Missing required sections or unexpected fields are reported as diagnostics.
- Crossposts are rejected like the original parser.
- CDN/media Discord URLs are normalized by the legacy parser.
- Parser output is written via temp file then replace, so existing parsed output is not deleted before replacement output is ready.

## Testing

Current tests include a full-schema parser fixture covering:

- designers
- versions
- rates
- files
- description
- instructions

Add golden fixtures before intentionally changing parser behavior.
