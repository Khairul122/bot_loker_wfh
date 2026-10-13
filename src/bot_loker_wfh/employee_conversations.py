"""Persist owner-to-employee web chats for the office activity monitor."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from .database import Connection

_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_MAX_CONTENT_LENGTH = 4000


def record_web_exchange(connection: Connection, employee_id: str, question: str, answer: str) -> str:
    """Store one owner question and employee answer under one conversation id."""
    if not isinstance(employee_id, str) or not _ID_RE.fullmatch(employee_id):
        raise ValueError("employee_id is invalid")
    question = question.strip() if isinstance(question, str) else ""
    answer = answer.strip() if isinstance(answer, str) else ""
    if not question or not answer:
        raise ValueError("question and answer must not be empty")
    if len(question) > _MAX_CONTENT_LENGTH or len(answer) > _MAX_CONTENT_LENGTH:
        raise ValueError("conversation message is too long")

    conversation_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    with connection:
        connection.executemany(
            "INSERT INTO employee_conversations "
            "(id, conversation_id, employee_id, speaker, channel, content, created_at) "
            "VALUES (?, ?, ?, ?, 'web_chat', ?, ?)",
            [
                (str(uuid.uuid4()), conversation_id, employee_id, "owner", question, created_at),
                (str(uuid.uuid4()), conversation_id, employee_id, "employee", answer, created_at),
            ],
        )
    return conversation_id
