# Architecture

Archiver-Bot keeps Discord-facing code thin and puts behavior in services.

## Layout

```text
src/
  app.py          Bot factory, service wiring, extension loading
  cogs/           Slash commands, context commands, and event listeners
  config/         Guild IDs, copy text, and environment settings
  models/         Runtime state and parser output shapes
  parser/         Archive post parser
  services/       Workflow logic
  storage/        Local JSON state store
```

## Startup

1. `main.py` calls `app.run_bot()`.
2. `create_bot()` loads settings and builds services.
3. `setup_hook()` initializes local state and loads cogs.
4. Commands are synced.

## Rules Of Thumb

- Put Discord UI and command parsing in `cogs/`.
- Put workflow behavior in `services/`.
- Put persistent data changes behind `StateService` / `StateStore`.
- Default outbound bot messages to no mentions.
- Keep guild-specific IDs in `config/settings.py`.
