"""Small SQLite meeting runtime: scheduling, attendance, notes, and status."""

from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from .database import sync_to_supabase

MAX_TITLE_LENGTH = 200
MAX_TEXT_LENGTH = 4000
MAX_PARTICIPANTS = 50
MAX_EVENTS = 200
_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_STATUSES = frozenset({"scheduled", "active", "completed", "cancelled"})
_EVENT_TYPES = frozenset({"join", "leave", "note", "decision", "action"})


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS meetings (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
            starts_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('scheduled', 'active', 'completed', 'cancelled')),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS meeting_participants (
            meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
            employee_id TEXT NOT NULL,
            PRIMARY KEY (meeting_id, employee_id)
        );
        CREATE TABLE IF NOT EXISTS meeting_events (
            id TEXT PRIMARY KEY,
            meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
            employee_id TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK (event_type IN ('join', 'leave', 'note', 'decision', 'action')),
            content TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 4000),
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_meeting_events ON meeting_events(meeting_id, created_at);
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


def _employee(value: Any) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ValueError("employee_id is invalid")
    return value


def _timestamp(value: Any) -> str:
    value = _text(value, "starts_at", 40)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("starts_at must be ISO-8601") from error
    if parsed.tzinfo is None:
        raise ValueError("starts_at must include timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _meeting(row) -> dict[str, Any]:
    meeting_id, title, starts_at, status, created_at = row
    return {"id": meeting_id, "title": title, "starts_at": starts_at, "status": status, "created_at": created_at}


def create_meeting(connection: sqlite3.Connection, title: str, starts_at: str, participants: list[str] | tuple[str, ...]) -> dict[str, Any]:
    title = _text(title, "title", MAX_TITLE_LENGTH)
    starts_at = _timestamp(starts_at)
    if not isinstance(participants, (list, tuple)) or len(participants) > MAX_PARTICIPANTS:
        raise ValueError(f"participants must contain 0-{MAX_PARTICIPANTS} employees")
    participants = [_employee(item) for item in participants]
    if len(set(participants)) != len(participants):
        raise ValueError("participants must be unique")
    meeting_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    with connection:
        connection.execute("INSERT INTO meetings VALUES (?, ?, ?, 'scheduled', ?)", (meeting_id, title, starts_at, created_at))
        connection.executemany("INSERT INTO meeting_participants VALUES (?, ?)", [(meeting_id, employee) for employee in participants])
    sync_to_supabase("meetings", {"id": meeting_id, "title": title, "starts_at": starts_at, "status": "scheduled", "created_at": created_at})
    if participants:
        sync_to_supabase("meeting_participants", [{"meeting_id": meeting_id, "employee_id": e} for e in participants])
    return get_meeting(connection, meeting_id)


def get_meeting(connection: sqlite3.Connection, meeting_id: str) -> dict[str, Any]:
    _text(meeting_id, "meeting_id", 100)
    row = connection.execute("SELECT id, title, starts_at, status, created_at FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
    if row is None:
        raise KeyError(meeting_id)
    result = _meeting(row)
    result["participants"] = [r[0] for r in connection.execute("SELECT employee_id FROM meeting_participants WHERE meeting_id = ? ORDER BY employee_id", (meeting_id,))]
    result["events"] = list_events(connection, meeting_id)
    return result


def set_status(connection: sqlite3.Connection, meeting_id: str, status: str) -> dict[str, Any]:
    _text(meeting_id, "meeting_id", 100)
    if status not in _STATUSES:
        raise ValueError("status is invalid")
    with connection:
        cursor = connection.execute("UPDATE meetings SET status = ? WHERE id = ?", (status, meeting_id))
    if cursor.rowcount != 1:
        raise KeyError(meeting_id)
    meeting = get_meeting(connection, meeting_id)
    sync_to_supabase("meetings", {k: meeting[k] for k in ("id", "title", "starts_at", "status", "created_at")})
    return meeting


def add_event(connection: sqlite3.Connection, meeting_id: str, employee_id: str, event_type: str, content: str) -> dict[str, Any]:
    _text(meeting_id, "meeting_id", 100)
    employee_id = _employee(employee_id)
    content = _text(content, "content", MAX_TEXT_LENGTH)
    if event_type not in _EVENT_TYPES:
        raise ValueError("event_type is invalid")
    if connection.execute("SELECT 1 FROM meetings WHERE id = ?", (meeting_id,)).fetchone() is None:
        raise KeyError(meeting_id)
    if connection.execute("SELECT COUNT(*) FROM meeting_events WHERE meeting_id = ?", (meeting_id,)).fetchone()[0] >= MAX_EVENTS:
        raise ValueError("meeting event limit reached")
    event_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    with connection:
        connection.execute("INSERT INTO meeting_events VALUES (?, ?, ?, ?, ?, ?)", (event_id, meeting_id, employee_id, event_type, content, created_at))
    event = {"id": event_id, "meeting_id": meeting_id, "employee_id": employee_id, "event_type": event_type, "content": content, "created_at": created_at}
    sync_to_supabase("meeting_events", event)
    return event


def list_events(connection: sqlite3.Connection, meeting_id: str) -> list[dict[str, Any]]:
    _text(meeting_id, "meeting_id", 100)
    rows = connection.execute("SELECT id, meeting_id, employee_id, event_type, content, created_at FROM meeting_events WHERE meeting_id = ? ORDER BY created_at, id", (meeting_id,)).fetchall()
    return [dict(zip(("id", "meeting_id", "employee_id", "event_type", "content", "created_at"), row)) for row in rows]


def run_dynamic_meeting(connection: Any, topic: str, participants: list[str]) -> dict[str, Any]:
    """Run dynamic multi-agent discussion using 9Router models and employee skills."""
    from .config import Settings
    from .employee_skills import load_employee_skills
    from .llm import OpenAICompatibleProvider

    settings = Settings.from_environment()
    provider = OpenAICompatibleProvider(
        settings.ninerouter_base_url,
        settings.ninerouter_api_key or "sk-dummy",
        settings.ninerouter_model or "LokerHouse",
    )

    from .office_events import bus as _bus

    ensure_schema(connection)
    starts_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    meeting = create_meeting(connection, topic, starts_at, participants)
    meeting_id = meeting["id"]
    set_status(connection, meeting_id, "active")
    _bus.publish({"type": "meeting", "status": "started", "meeting_id": meeting_id,
                  "task": topic, "participants": list(participants)})

    transcript = []
    # Conversation turns
    for emp in participants:
        skill_text = ""
        try:
            skill_text = load_employee_skills(emp)[:1500]
        except Exception:
            pass

        prompt = (
            f"Konteks: Rapat tim kantor Loker House.\n"
            f"Topik rapat: '{topic}'.\n"
            f"Identitas Anda: Karyawan '{emp}'.\n"
            f"Skill & peran Anda:\n{skill_text}\n\n"
            f"Beri tanggapan padat (1-2 kalimat) sesuai keahlian Anda mengenai topik tersebut. "
            f"Sampaikan solusi konkret, bukan basa-basi."
        )
        try:
            res = provider.complete([{"role": "user", "content": prompt}])
            speech = res.text.strip()
        except Exception:
            speech = f"Saya siap mendukung topik {topic} sesuai fokus tim saya."

        add_event(connection, meeting_id, emp, "note", speech)
        _bus.publish({"type": "meeting", "status": "speaking", "meeting_id": meeting_id,
                      "task": topic, "employee": emp, "content": speech})
        transcript.append({"employee": emp, "speech": speech})

    # Summary turn
    decision_prompt = (
        f"Rangkum hasil rapat tim dengan topik '{topic}'.\n"
        f"Pernyataan tim:\n"
        + "\n".join([f"- {t['employee']}: {t['speech']}" for t in transcript])
        + "\nBuatkan 1 kesimpulan keputusan aksi konkret."
    )
    try:
        dec_res = provider.complete([{"role": "user", "content": decision_prompt}])
        decision = dec_res.text.strip()
    except Exception:
        decision = f"Tim sepakat mengeksekusi prioritas terkait {topic}."

    add_event(connection, meeting_id, participants[0] if participants else "cora", "decision", decision)
    set_status(connection, meeting_id, "completed")
    _bus.publish({"type": "meeting", "status": "completed", "meeting_id": meeting_id,
                  "task": topic, "employee": "owner", "content": decision,
                  "participants": list(participants)})

    return {
        "id": meeting_id,
        "title": topic,
        "participants": participants,
        "status": "completed",
        "transcript": transcript,
        "decision": decision,
    }
