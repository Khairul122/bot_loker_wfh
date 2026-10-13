"""Persist owner feedback and promote explicit corrections into employee memory."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from .company import EMPLOYEES
from .database import Connection
from .employee_memory import remember

_EMPLOYEE_IDS = frozenset(employee["id"] for employee in EMPLOYEES)
_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_KINDS = frozenset({"helpful", "correction", "lesson"})
_MAX_NOTE_LENGTH = 1000


def save_feedback(
    connection: Connection,
    employee_id: str,
    conversation_id: str,
    kind: str,
    note: str = "",
) -> dict[str, Any]:
    """Save one owner decision for a real web-chat answer.

    Only the owner's note is promoted into memory. The AI response itself is never
    treated as a correction or lesson.
    """
    if not isinstance(employee_id, str) or employee_id not in _EMPLOYEE_IDS:
        raise ValueError("employee_id is invalid")
    if not isinstance(conversation_id, str):
        raise ValueError("conversation_id is invalid")
    try:
        conversation_id = str(uuid.UUID(conversation_id))
    except (ValueError, AttributeError) as error:
        raise ValueError("conversation_id is invalid") from error
    if not isinstance(kind, str) or kind not in _KINDS:
        raise ValueError("kind is invalid")
    if not isinstance(note, str):
        raise ValueError("note is invalid")
    note = note.strip()
    if len(note) > _MAX_NOTE_LENGTH or (kind in {"correction", "lesson"} and not note):
        raise ValueError("note must contain 1-1000 characters for a correction or lesson")

    exists = connection.execute(
        "SELECT 1 FROM employee_conversations "
        "WHERE conversation_id = ? AND employee_id = ? AND speaker = 'employee' LIMIT 1",
        (conversation_id, employee_id),
    ).fetchone()
    if not exists:
        raise KeyError("conversation_not_found")

    feedback_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    memory_id = None
    if kind in {"correction", "lesson"}:
        memory_kind = "correction" if kind == "correction" else "observation"
        memory = remember(
            connection,
            employee_id,
            note,
            kind=memory_kind,
            source=f"chat-feedback:{conversation_id}",
            importance=0.95,
            metadata={"conversation_id": conversation_id, "owner_feedback": kind},
            replace_source=True,
        )
        memory_id = memory["id"]
    else:
        # Replacing a previous correction with positive feedback removes its lesson.
        connection.execute(
            "DELETE FROM employee_memory WHERE employee_id = ? AND source = ?",
            (employee_id, f"chat-feedback:{conversation_id}"),
        )

    with connection:
        row = connection.execute(
            "INSERT INTO employee_chat_feedback "
            "(id, conversation_id, employee_id, kind, note, memory_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (conversation_id) DO UPDATE SET "
            "employee_id = EXCLUDED.employee_id, kind = EXCLUDED.kind, note = EXCLUDED.note, "
            "memory_id = EXCLUDED.memory_id, created_at = EXCLUDED.created_at "
            "RETURNING id, conversation_id, employee_id, kind, note, memory_id, created_at",
            (feedback_id, conversation_id, employee_id, kind, note, memory_id, created_at),
        ).fetchone()
    keys = ("id", "conversation_id", "employee_id", "kind", "note", "memory_id", "created_at")
    return dict(zip(keys, row))
