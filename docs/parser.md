# Parser

The parser converts archive post text into JSON files.

## Files

- `src/parser/legacy.py`: strict archive post parser
- `src/models/message.py`: parser output shapes
- `src/parser/core.py`: shared helpers
- `src/services/parser_service.py`: Discord thread collection and file writing

## Commands

- `/parse_post`
- `/parse_channel`
- `/parse_archive`

## Output

```text
ARCHIVER_DATA_DIR/parsed/<thread_id>.json
```

## Behavior

- Reads default messages from archive threads.
- Builds a mention ID to username lookup before parsing.
- Requires the archive post format expected by `message_parse`.
- Rejects crossposts.
- Normalizes Discord CDN/media URLs.
- Writes output via temp file then replace.

Add parser fixtures before changing parser behavior.
