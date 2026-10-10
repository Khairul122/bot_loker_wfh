# Migrations

Postgres (Supabase) schema. `database.apply_schema()` runs each `NNN_*.sql` once (tracked in
`schema_migrations`) and re-applies `seed.sql` (idempotent defaults) on every call.
Add a new numbered file for schema changes.
