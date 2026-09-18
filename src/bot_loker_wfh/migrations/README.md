# Database Migrations

SQLite migrations for the MVP live in this directory.

- `001_initial_schema.sql` creates the initial tables, indexes, uniqueness constraints, and default filter row.
- Apply migrations from a local environment with `python -m bot_loker_wfh init-db`.

All timestamp defaults are stored as UTC ISO-8601 text ending in `Z`.

