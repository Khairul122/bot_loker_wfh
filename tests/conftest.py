"""Test database: one throwaway schema on the Supabase Postgres, emptied before every DB test.

Tests never touch the real tables: connections made through `database.connect()` are pinned to
`BOT_DB_SCHEMA` (a `t_<random>` schema created on first use and dropped when the session ends).
Tests that never open a connection pay nothing.
"""

import os
import uuid
from pathlib import Path

import pytest

from bot_loker_wfh import config, database


def _db_url_from_dotenv() -> None:
    """Read only SUPABASE_DB_URL from .env so other local settings never leak into tests."""
    if os.getenv("SUPABASE_DB_URL"):
        return
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("SUPABASE_DB_URL="):
            os.environ["SUPABASE_DB_URL"] = line.partition("=")[2].strip()


_db_url_from_dotenv()
_session: dict = {}


def _ensure_schema() -> list[str]:
    if "tables" in _session:
        return _session["tables"]
    schema = f"t_{uuid.uuid4().hex[:10]}"
    admin = database.connect(schema="public")
    admin.execute(f"CREATE SCHEMA {schema}")
    admin.commit()
    os.environ["BOT_DB_SCHEMA"] = schema
    connection = database.connect(schema=schema)
    database.apply_schema(connection)
    _session["tables"] = [
        row[0]
        for row in connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = ? AND tablename <> 'schema_migrations'",
            (schema,),
        )
    ]
    _session["schema"] = schema
    connection.close()
    admin.close()
    return _session["tables"]


def pytest_sessionfinish(session, exitstatus):
    schema = _session.get("schema")
    if not schema:
        return
    admin = database.connect(schema="public")
    admin.execute(f"DROP SCHEMA {schema} CASCADE")
    admin.commit()
    admin.close()
    os.environ.pop("BOT_DB_SCHEMA", None)


@pytest.fixture(autouse=True)
def _database_per_test(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    database._ready.clear()
    real_connect = database.connect
    fresh = {"done": False}

    def connect(schema=None):
        if not fresh["done"]:
            fresh["done"] = True
            tables = _ensure_schema()
            cleaner = real_connect()
            cleaner.execute("TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY CASCADE")
            cleaner.commit()
            cleaner.close()
        return real_connect(schema)

    monkeypatch.setattr(database, "connect", connect)
    yield
    database.close_all()
