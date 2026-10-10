"""Bounded, validated employee learning records backed by SQLite.

No model calls happen here. Callers store explicit observations, preferences,
corrections, or outcomes and retrieve them for later use.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

MAX_RECORDS_PER_EMPLOYEE = 100
MAX_CONTENT_LENGTH = 2000
MAX_SOURCE_LENGTH = 100
MAX_KIND_LENGTH = 40
_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_KINDS = frozenset({"observation", "preference", "correction", "outcome"})


def ensure_schema(connection: sqlite3.Connection) -> None:
    """Create memory tables. Safe to call for every connection."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS employee_memory (
            id TEXT PRIMARY KEY,
            employee_id TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('observation', 'preference', 'correction', 'outcome')),
            content TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 2000),
            source TEXT NOT NULL CHECK (length(source) BETWEEN 1 AND 100),
            importance REAL NOT NULL CHECK (importance >= 0.0 AND importance <= 1.0),
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_employee_memory_lookup
            ON employee_memory (employee_id, importance DESC, created_at DESC);
        """
    )
    connection.commit()


def _text(value: Any, name: str, limit: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    value = value.strip()
    if not value or len(value) > limit:
        raise ValueError(f"{name} must contain 1-{limit} characters")
    return value


def _employee_id(value: Any) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ValueError("employee_id is invalid")
    return value


def _metadata(value: Any) -> str:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("metadata must be an object")
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise ValueError("metadata must be JSON serializable") from error
    if len(encoded) > 4000:
        raise ValueError("metadata is too large")
    return encoded


def _row(row: sqlite3.Row | tuple) -> dict[str, Any]:
    keys = ("id", "employee_id", "kind", "content", "source", "importance", "metadata", "created_at")
    result = dict(zip(keys, row))
    result["metadata"] = json.loads(result["metadata"])
    return result


def remember(
    connection: sqlite3.Connection,
    employee_id: str,
    content: str,
    *,
    kind: str = "observation",
    source: str = "system",
    importance: float = 0.5,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Store one explicit learning record and prune oldest low-value records."""
    employee_id = _employee_id(employee_id)
    content = _text(content, "content", MAX_CONTENT_LENGTH)
    kind = _text(kind, "kind", MAX_KIND_LENGTH)
    source = _text(source, "source", MAX_SOURCE_LENGTH)
    if kind not in _KINDS:
        raise ValueError("kind is invalid")
    if isinstance(importance, bool) or not isinstance(importance, (int, float)) or not 0 <= importance <= 1:
        raise ValueError("importance must be between 0 and 1")
    encoded_metadata = _metadata(metadata)
    record_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    with connection:
        connection.execute(
            "INSERT INTO employee_memory "
            "(id, employee_id, kind, content, source, importance, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (record_id, employee_id, kind, content, source, float(importance), encoded_metadata, created_at),
        )
        connection.execute(
            "DELETE FROM employee_memory WHERE employee_id = ? AND id NOT IN "
            "(SELECT id FROM employee_memory WHERE employee_id = ? "
            "ORDER BY (id = ?) DESC, importance DESC, created_at DESC LIMIT ?)",
            (employee_id, employee_id, record_id, MAX_RECORDS_PER_EMPLOYEE),
        )
    row = connection.execute("SELECT id, employee_id, kind, content, source, importance, metadata, created_at "
                             "FROM employee_memory WHERE id = ?", (record_id,)).fetchone()
    return _row(row)


def list_memories(connection: sqlite3.Connection, employee_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Return highest-value recent records, with a hard retrieval cap."""
    employee_id = _employee_id(employee_id)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_RECORDS_PER_EMPLOYEE:
        raise ValueError(f"limit must be between 1 and {MAX_RECORDS_PER_EMPLOYEE}")
    rows = connection.execute(
        "SELECT id, employee_id, kind, content, source, importance, metadata, created_at "
        "FROM employee_memory WHERE employee_id = ? ORDER BY importance DESC, created_at DESC LIMIT ?",
        (employee_id, limit),
    ).fetchall()
    return [_row(row) for row in rows]


def delete_memory(connection: sqlite3.Connection, memory_id: str) -> bool:
    """Delete one record by ID. Return whether record existed."""
    _text(memory_id, "memory_id", 100)
    with connection:
        cursor = connection.execute("DELETE FROM employee_memory WHERE id = ?", (memory_id,))
    return cursor.rowcount == 1
