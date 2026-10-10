# Project Instructions

## Tech stack

- Python >= 3.11.
- Package source under `src/bot_loker_wfh/`.
- Supabase Postgres only (via `psycopg`, connection string in `SUPABASE_DB_URL`). Schema lives in `src/bot_loker_wfh/migrations/`; tables are in the `loker` schema.
- Telegram controls the long-running bot.
- BrowserMCP (your own Chrome) is the form-assist engine.
- Runtime dependency is `psycopg` only; anything else needs an optional extra.

## Build and run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m bot_loker_wfh init-db
python -m bot_loker_wfh run-bot
```

Useful checks:

```powershell
python -m bot_loker_wfh check-llm
python -m bot_loker_wfh check-browser
python -m pytest -q
```

Form assist uses BrowserMCP (`npx @browsermcp/mcp`) with your own Chrome; no Playwright.

## Project structure

- `__main__.py`: CLI command dispatch.
- `bot.py`: Telegram polling and cycle orchestration.
- `scheduler.py`: source fetch scheduling.
- `pipeline.py`: scoring and eligibility processing.
- `database.py` and `migrations/`: Postgres connection wrapper and schema.
- `telegram_*.py`: Telegram auth, commands, approval, notifications.
- `form_agent/`: guarded form planning and execution.
- `office_server.py` and `office/`: local 3D office UI.
- `tests/`: automated tests and fixtures.
- `data/`: local database and user data. Treat as sensitive and do not commit secrets.

Full map: `docs/ONBOARDING.md`.

## Code conventions

- Use `snake_case` for modules, functions, and variables. Use `PascalCase` for classes.
- Inject external clients, clock, sleep, process spawn, logger, and submitter where tests need control.
- Keep business status changes inside centralized transition services.
- Keep fetchers idempotent through source identity and database uniqueness constraints.
- Do not log CV data, cover letters, tokens, credentials, request bodies, or provider error text.
- Convert external failures to sanitized error codes before logging.
- Prefer Postgres and standard library over new dependencies.

## Safety rules

- External job APIs stay disabled unless `EXTERNAL_JOBS_ENABLED=true`.
- Telegram commands and callbacks require allowlisted chat IDs.
- Form assist must stop before Submit and never solve CAPTCHA.
- Treat stale or replayed approval callbacks as no-op failures.
- Production submission stays disabled until reviewed target allowlist, target policy, secure upload handling, and manual production test exist.
- Do not edit `.env` or user profile data unless explicitly requested.

## Database changes

Add a new migration under `src/bot_loker_wfh/migrations/` for schema changes. Update `database.py` when migration application order needs a new file. Add or update schema tests. Tests apply migrations to a throwaway `t_*` schema, never to the real tables.

## Testing

- Add regression coverage for non-trivial behavior.
- Tests use the throwaway Postgres schema from `tests/conftest.py` (needs `SUPABASE_DB_URL`), fixtures, and fake clients. `pytest -n 8` (pytest-xdist) keeps the suite fast.
- Do not call real job APIs, Telegram, LLM providers, or browsers in unit tests.
- Run `python -m pytest -q` before claiming completion.
