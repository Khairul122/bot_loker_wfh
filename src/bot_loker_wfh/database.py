"""SQLite schema setup for the MVP."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import urlparse


SCHEMA_PATH = Path(__file__).with_name("migrations") / "001_initial_schema.sql"


def apply_schema(connection: sqlite3.Connection) -> None:
    """Create the MVP schema and default filter configuration."""
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    connection.commit()


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
