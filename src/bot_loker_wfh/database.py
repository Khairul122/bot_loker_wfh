"""Supabase Postgres database layer (psycopg).

Exposes a small connection wrapper so the rest of the code keeps one calling style:
`connection.execute(sql, params)` with `?` placeholders, rows readable by index or column
name, `with connection:` for a commit/rollback block, `executescript` for multi-statement SQL.
"""

from __future__ import annotations

import contextlib
import itertools
import os
import re
import weakref
from pathlib import Path
from typing import Any

import psycopg
from psycopg import errors as pg_errors
from psycopg.adapt import Loader
from psycopg.types.numeric import Int2Dumper

MIGRATIONS_DIR = Path(__file__).with_name("migrations")
SEED_PATH = MIGRATIONS_DIR / "seed.sql"

Error = psycopg.Error
IntegrityError = pg_errors.IntegrityError
UniqueViolation = pg_errors.UniqueViolation
OperationalError = psycopg.OperationalError
UndefinedTable = pg_errors.UndefinedTable


class DatabaseNotConfigured(RuntimeError):
    """Raised when SUPABASE_DB_URL is missing."""


def database_url() -> str:
    url = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL", "")
    if not url.startswith(("postgresql://", "postgres://")):
        raise DatabaseNotConfigured("SUPABASE_DB_URL is not set")
    return url


def database_configured() -> bool:
    try:
        database_url()
    except DatabaseNotConfigured:
        return False
    return True


class Row(tuple):
    """A result row readable by index or by column name."""

    _cols: tuple[str, ...]

    def __new__(cls, cols, values):
        row = super().__new__(cls, values)
        row._cols = tuple(cols)
        return row

    def __getitem__(self, key):
        if isinstance(key, str):
            return tuple.__getitem__(self, self._cols.index(key))
        return tuple.__getitem__(self, key)

    def keys(self) -> list[str]:
        return list(self._cols)


def _row_factory(cursor):
    cols = [column.name for column in cursor.description] if cursor.description else []
    return lambda values: Row(cols, values)


class _FloatLoader(Loader):
    """numeric (AVG, SUM of reals) -> float, so results stay JSON serializable."""

    def load(self, data):
        return float(bytes(data))


_WRITE = re.compile(r"^\s*(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE|SELECT\s+pg_advisory)", re.I)
_LITERAL = re.compile(r"('(?:[^']|'')*')")
_live: "weakref.WeakSet[Connection]" = weakref.WeakSet()
_savepoints = itertools.count(1)


def _translate(sql: str, has_params: bool) -> str:
    """qmark -> psycopg placeholders; `%` is escaped only when parameters are passed."""
    if not has_params:
        return sql
    parts = _LITERAL.split(sql)
    for i, part in enumerate(parts):
        part = part.replace("%", "%%")
        parts[i] = part if i % 2 else part.replace("?", "%s")
    return "".join(parts)


class Cursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def fetchmany(self, size: int = 1):
        return self._cursor.fetchmany(size)

    def __iter__(self):
        return iter(self._cursor)

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description


class Connection:
    def __init__(self, raw: "psycopg.Connection"):
        self._raw = raw
        self._dirty = False
        raw.adapters.register_loader("numeric", _FloatLoader)
        raw.adapters.register_dumper(bool, Int2Dumper)  # INTEGER flag columns accept True/False
        _live.add(self)

    # sqlite3 compatibility: callers assign this; rows are always name-addressable.
    row_factory = None

    def _begin_scope(self, write: bool) -> None:
        # reads outside a write transaction run autocommit so no idle transaction lingers
        if self._raw.info.transaction_status == psycopg.pq.TransactionStatus.IDLE:
            self._raw.autocommit = not write and not self._dirty

    def execute(self, sql: str, params=None) -> Cursor:
        params = tuple(params) if params else None
        query = _translate(sql, params is not None)
        write = bool(_WRITE.match(query))
        if write:
            self._dirty = True
        self._begin_scope(write)
        cursor = self._raw.cursor(row_factory=_row_factory)
        cursor.execute(query, params)
        return Cursor(cursor)

    def executemany(self, sql: str, seq) -> Cursor:
        rows = [tuple(item) for item in seq]
        self._dirty = True
        self._begin_scope(True)
        cursor = self._raw.cursor(row_factory=_row_factory)
        if rows:
            cursor.executemany(_translate(sql, True), rows)
        return Cursor(cursor)

    def executescript(self, script: str) -> None:
        self._dirty = True
        self._begin_scope(True)
        self._raw.execute(script)  # no parameters: multiple statements allowed

    def begin(self) -> None:
        """Open a write transaction now (rows read afterwards can be locked with FOR UPDATE)."""
        self._dirty = True
        self._begin_scope(True)
        self._raw.execute("SELECT 1")

    def commit(self) -> None:
        self._raw.commit()
        self._dirty = False

    def rollback(self) -> None:
        self._raw.rollback()
        self._dirty = False

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._raw.close()

    @contextlib.contextmanager
    def savepoint(self):
        """Let one statement fail (e.g. a duplicate insert) without aborting the transaction."""
        name = f"sp_{next(_savepoints)}"
        self._dirty = True
        self._begin_scope(True)
        self._raw.execute(f"SAVEPOINT {name}")
        try:
            yield
        except BaseException:
            self._raw.execute(f"ROLLBACK TO SAVEPOINT {name}")
            raise
        else:
            self._raw.execute(f"RELEASE SAVEPOINT {name}")

    def __enter__(self) -> "Connection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()


def connect(schema: str | None = None) -> Connection:
    """Open a connection to Supabase Postgres (optionally pinned to one schema, for tests)."""
    schema = schema or os.getenv("BOT_DB_SCHEMA")
    options = f"-c search_path={schema}" if schema else None
    raw = psycopg.connect(database_url(), options=options, connect_timeout=15, prepare_threshold=None)
    return Connection(raw)


@contextlib.contextmanager
def session():
    """One short-lived connection: commit on success, roll back on error, always close."""
    connection = connect()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def close_all() -> None:
    for connection in list(_live):
        connection.close()


def _applied_versions(connection: Connection) -> set[str]:
    exists = connection.execute("SELECT to_regclass('schema_migrations') IS NOT NULL").fetchone()[0]
    if not exists:
        return set()
    return {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}


def apply_schema(connection: Connection) -> None:
    """Apply pending migrations once, then (re)apply idempotent seed rows."""
    applied = _applied_versions(connection)
    pending = [p for p in sorted(MIGRATIONS_DIR.glob("[0-9]*.sql")) if p.name not in applied]
    if pending:
        connection.execute("SELECT pg_advisory_xact_lock(7001)")
        connection.executescript(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT now()::text);"
            "ALTER TABLE schema_migrations ENABLE ROW LEVEL SECURITY;"
        )
        applied = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
        for path in pending:
            if path.name in applied:
                continue
            connection.executescript(path.read_text(encoding="utf-8"))
            connection.execute("INSERT INTO schema_migrations (version) VALUES (?)", (path.name,))
    connection.executescript(SEED_PATH.read_text(encoding="utf-8"))
    connection.commit()


def initialize_database() -> None:
    """Create/upgrade the schema on the configured Supabase database."""
    connection = connect()
    try:
        apply_schema(connection)
    finally:
        connection.close()


def open_db() -> Connection:
    """Open a connection with the schema applied."""
    connection = connect()
    apply_schema(connection)
    return connection
