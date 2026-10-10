"""Supabase cloud database layer and local sqlite persistence integration."""

from __future__ import annotations

import datetime
import json
import logging
import os
import sqlite3
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_SUPABASE_URL = "https://iujhspshmggmptoatbof.supabase.co"


def _supabase_url() -> str:
    # Read lazily: .env is loaded after this module is imported.
    return os.getenv("SUPABASE_URL") or DEFAULT_SUPABASE_URL


def _supabase_key() -> str:
    # Service-role key preferred: RLS restricts app_settings/office_character_state to it.
    return (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_SERVICE_KEY")
        or os.getenv("SUPABASE_KEY", "")
    )


class SupabaseUnavailable(RuntimeError):
    """Raised when Supabase is not configured or a request fails."""

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DEFAULT_DB_PATH = DATA_DIR / "app.db"

SCHEMA_PATH = Path(__file__).with_name("migrations") / "001_initial_schema.sql"
SCHEMA_002_PATH = Path(__file__).with_name("migrations") / "002_llm_and_form_agent.sql"
SCHEMA_003_PATH = Path(__file__).with_name("migrations") / "003_app_settings.sql"
SCHEMA_004_PATH = Path(__file__).with_name("migrations") / "004_office_desk.sql"
SCHEMA_005_PATH = Path(__file__).with_name("migrations") / "005_office_state.sql"

EXTRA_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS employee_memories (
    id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    importance REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS office_meetings (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled',
    starts_at TEXT NOT NULL,
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS office_meeting_events (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

INITIAL_CHARACTER_COORDINATES = [
    ("owner", "owner", 2.0, 0.0, 9.0, 0.0),
    ("bimo", "staff", 8.5, 0.0, 2.1, 1.57),
    ("cora", "staff", 5.2, 0.0, -3.4, 3.14),
    ("dela", "staff", -4.1, 0.0, 6.2, 0.0),
    ("eli", "staff", 7.0, 0.0, -1.2, 0.78),
    ("faris", "staff", -6.5, 0.0, -5.0, 1.57),
    ("gery", "staff", 3.8, 0.0, 4.5, 2.1),
    ("ivan", "staff", -2.2, 0.0, -8.1, 0.0),
    ("kalia", "staff", 9.1, 0.0, -4.2, 1.2),
    ("leva", "staff", -8.0, 0.0, 1.5, 2.7),
    ("lido", "staff", 1.4, 0.0, -6.0, 0.5),
    ("lulu", "staff", -5.0, 0.0, 3.0, 1.8),
    ("nara", "staff", 6.0, 0.0, 8.0, 0.0),
    ("reno", "staff", -1.0, 0.0, 5.0, 3.0),
    ("rima", "staff", 4.0, 0.0, -7.0, 1.4),
    ("sari", "staff", -7.5, 0.0, -2.5, 0.2),
    ("subi", "staff", 2.5, 0.0, -2.5, 2.5),
    ("tama", "staff", -3.5, 0.0, -1.5, 1.1),
    ("tara", "staff", 8.0, 0.0, 5.5, 0.8),
    ("tegar", "staff", 0.0, 0.0, 0.0, 0.0),
]


def sqlite_path_from_url(database_url: str) -> Path:
    if database_url.startswith("sqlite:///"):
        path_str = database_url[len("sqlite///"):]
        return Path(path_str).resolve()
    return Path(database_url).resolve()


def apply_schema(connection: sqlite3.Connection) -> None:
    """Apply database migrations and extra schemas."""
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    _ensure_embedding_columns(connection)
    _apply_002_schema(connection)
    _apply_003_schema(connection)
    connection.executescript(SCHEMA_004_PATH.read_text(encoding="utf-8"))
    connection.executescript(SCHEMA_005_PATH.read_text(encoding="utf-8"))
    connection.executescript(EXTRA_TABLES_SQL)
    connection.commit()


def _ensure_embedding_columns(connection: sqlite3.Connection) -> None:
    job_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
    }
    for column in ("embedding_model", "embedding_version", "notified_at"):
        if column not in job_columns:
            connection.execute(f"ALTER TABLE jobs ADD COLUMN {column} TEXT")


def _apply_002_schema(connection: sqlite3.Connection) -> None:
    app_columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(applications)").fetchall()
    }
    for column in ("llm_provider", "llm_model"):
        if column not in app_columns:
            connection.execute(f"ALTER TABLE applications ADD COLUMN {column} TEXT")

    filter_columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(filters)").fetchall()
    }
    if "max_bids" not in filter_columns:
        connection.execute("ALTER TABLE filters ADD COLUMN max_bids INTEGER DEFAULT NULL")

    lead_columns = {row[1] for row in connection.execute("PRAGMA table_info(leads)").fetchall()}
    if "proposal" not in lead_columns:
        connection.execute("ALTER TABLE leads ADD COLUMN proposal TEXT")
    if "comment" not in lead_columns:
        connection.execute("ALTER TABLE leads ADD COLUMN comment TEXT")

    statements = SCHEMA_002_PATH.read_text(encoding="utf-8").split(";")
    for stmt in statements:
        stmt = stmt.strip()
        if not stmt or stmt.startswith("ALTER TABLE applications ADD COLUMN llm_"):
            continue
        connection.execute(stmt)


def _apply_003_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_003_PATH.read_text(encoding="utf-8"))


def initialize_database(database_url: str = "sqlite:///data/app.db") -> Path:
    """Initialize database and ensure migrations applied."""
    database_path = sqlite_path_from_url(database_url)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        apply_schema(connection)
    return database_path


def supabase_configured() -> bool:
    return bool(_supabase_key())


def supabase_request(
    table: str,
    *,
    method: str = "GET",
    data: Any = None,
    query: dict[str, str] | None = None,
    prefer: str | None = None,
    timeout: float = 5.0,
) -> Any:
    """Call the Supabase REST endpoint. Raises SupabaseUnavailable on any failure."""
    key = _supabase_key()
    if not key:
        raise SupabaseUnavailable("supabase key not configured")
    url = f"{_supabase_url().rstrip('/')}/rest/v1/{table}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
    except Exception as error:  # URLError, HTTPError, timeout...
        raise SupabaseUnavailable(str(error)) from error
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def sync_to_supabase(table: str, data: dict[str, Any] | list[dict[str, Any]]) -> None:
    """Best-effort upsert to Supabase; never raises (callers treat it as a cache write)."""
    if not supabase_configured():
        return
    try:
        supabase_request(table, method="POST", data=data, prefer="resolution=merge-duplicates")
    except SupabaseUnavailable:
        # sanitized: table name only, never the provider error text or the payload
        logging.getLogger(__name__).warning("supabase_sync_failed table=%s", table)


def open_db(database_path: str | Path | None = None) -> sqlite3.Connection:
    """Open database connection and apply schema."""
    target = Path(database_path) if database_path else DEFAULT_DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    return conn
