"""SQLite schema setup for the MVP."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import urlparse


SCHEMA_PATH = Path(__file__).with_name("migrations") / "001_initial_schema.sql"
SCHEMA_002_PATH = Path(__file__).with_name("migrations") / "002_llm_and_form_agent.sql"
SCHEMA_003_PATH = Path(__file__).with_name("migrations") / "003_app_settings.sql"
SCHEMA_004_PATH = Path(__file__).with_name("migrations") / "004_office_desk.sql"
SCHEMA_005_PATH = Path(__file__).with_name("migrations") / "005_office_state.sql"


def apply_schema(connection: sqlite3.Connection) -> None:
    """Create the MVP schema and default filter configuration."""
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    _ensure_embedding_columns(connection)
    _apply_002_schema(connection)
    _apply_003_schema(connection)
    connection.executescript(SCHEMA_004_PATH.read_text(encoding="utf-8"))
    connection.executescript(SCHEMA_005_PATH.read_text(encoding="utf-8"))
    connection.commit()


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

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS llm_calls (
          id TEXT PRIMARY KEY,
          run_id TEXT,
          task TEXT NOT NULL,
          provider TEXT NOT NULL,
          model TEXT NOT NULL,
          attempt INTEGER NOT NULL DEFAULT 1,
          status TEXT NOT NULL,
          error_code TEXT,
          latency_ms INTEGER,
          prompt_tokens INTEGER,
          completion_tokens INTEGER,
          application_id TEXT REFERENCES applications(id),
          created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );
        CREATE INDEX IF NOT EXISTS idx_llm_calls_created ON llm_calls(created_at);

        CREATE TABLE IF NOT EXISTS ats_registry (
          id TEXT PRIMARY KEY,
          ats_name TEXT NOT NULL,
          host TEXT NOT NULL UNIQUE,
          mode TEXT NOT NULL CHECK (mode IN ('auto_fill', 'assist')),
          open_button_label TEXT,
          verified_at TEXT,
          active INTEGER NOT NULL DEFAULT 1
        );

        INSERT OR IGNORE INTO ats_registry (id, ats_name, host, mode, open_button_label) VALUES
          ('gh-1', 'Greenhouse', 'job-boards.greenhouse.io', 'auto_fill', NULL),
          ('gh-2', 'Greenhouse', 'boards.greenhouse.io', 'auto_fill', NULL),
          ('lv-1', 'Lever', 'jobs.lever.co', 'auto_fill', 'Apply for this job'),
          ('lv-2', 'Lever', 'jobs.eu.lever.co', 'auto_fill', 'Apply for this job'),
          ('ab-1', 'Ashby', 'jobs.ashbyhq.com', 'assist', 'Apply'),
          ('wk-1', 'Workable', 'apply.workable.com', 'assist', 'Apply for this job'),
          ('sr-1', 'SmartRecruiters', 'jobs.smartrecruiters.com', 'assist', 'I''m interested'),
          ('kb-1', 'Kalibrr', 'www.kalibrr.com', 'assist', 'Apply');

        CREATE TABLE IF NOT EXISTS form_sessions (
          id TEXT PRIMARY KEY,
          application_id TEXT NOT NULL REFERENCES applications(id),
          engine TEXT NOT NULL,
          host TEXT NOT NULL,
          mode TEXT NOT NULL,
          page_number INTEGER NOT NULL DEFAULT 1,
          status TEXT NOT NULL,
          filled_count INTEGER NOT NULL DEFAULT 0,
          ai_answer_count INTEGER NOT NULL DEFAULT 0,
          manual_count INTEGER NOT NULL DEFAULT 0,
          skipped_protected_count INTEGER NOT NULL DEFAULT 0,
          captcha INTEGER NOT NULL DEFAULT 0,
          tool_calls INTEGER NOT NULL DEFAULT 0,
          error_code TEXT,
          user_feedback TEXT,
          started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
          finished_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_form_sessions_application ON form_sessions(application_id);

        CREATE TABLE IF NOT EXISTS form_field_events (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL REFERENCES form_sessions(id),
          label TEXT NOT NULL,
          role TEXT NOT NULL,
          field_class TEXT NOT NULL,
          action TEXT NOT NULL,
          source TEXT,
          reason TEXT,
          confidence REAL
        );
        CREATE INDEX IF NOT EXISTS idx_form_field_events_session ON form_field_events(session_id);
        """
    )


def _apply_003_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_003_PATH.read_text(encoding="utf-8"))


def sqlite_path_from_url(database_url: str) -> Path:
    """Return a local SQLite path from a sqlite:/// URL."""
    parsed = urlparse(database_url)
    if parsed.scheme != "sqlite":
        raise ValueError("Only sqlite database URLs are supported in the MVP scaffold")
    if parsed.netloc:
        raise ValueError("SQLite database URL must use a local path")
    return Path(parsed.path.lstrip("/"))


def initialize_database(database_url: str) -> Path:
    """Create the SQLite database file and apply the MVP schema."""
    database_path = sqlite_path_from_url(database_url)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        apply_schema(connection)
    return database_path


def _ensure_embedding_columns(connection: sqlite3.Connection) -> None:
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
    }
    for column in ("embedding_model", "embedding_version", "notified_at"):
        if column not in columns:
            connection.execute(f"ALTER TABLE jobs ADD COLUMN {column} TEXT")
    attempt_columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(submission_attempts)"
        ).fetchall()
    }
    for column in ("confirmation_url", "confirmation_reference"):
        if column not in attempt_columns:
            connection.execute(
                f"ALTER TABLE submission_attempts ADD COLUMN {column} TEXT"
            )
