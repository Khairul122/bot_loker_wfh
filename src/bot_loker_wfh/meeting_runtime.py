"""Meeting runtime (Supabase Postgres): scheduling, attendance, notes, and status."""

from __future__ import annotations

import re
from .database import Connection
import uuid
from datetime import datetime, timezone
from typing import Any

MAX_TITLE_LENGTH = 200
MAX_TEXT_LENGTH = 4000
MAX_PARTICIPANTS = 50
MAX_EVENTS = 200
_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_STATUSES = frozenset({"scheduled", "active", "completed", "cancelled"})
_EVENT_TYPES = frozenset({"join", "leave", "note", "decision", "action"})


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


def create_meeting(connection: Connection, title: str, starts_at: str, participants: list[str] | tuple[str, ...]) -> dict[str, Any]:
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
    return get_meeting(connection, meeting_id)


def get_meeting(connection: Connection, meeting_id: str) -> dict[str, Any]:
    _text(meeting_id, "meeting_id", 100)
    row = connection.execute("SELECT id, title, starts_at, status, created_at FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
    if row is None:
        raise KeyError(meeting_id)
    result = _meeting(row)
    result["participants"] = [r[0] for r in connection.execute("SELECT employee_id FROM meeting_participants WHERE meeting_id = ? ORDER BY employee_id", (meeting_id,))]
    result["events"] = list_events(connection, meeting_id)
    return result


def set_status(connection: Connection, meeting_id: str, status: str) -> dict[str, Any]:
    _text(meeting_id, "meeting_id", 100)
    if status not in _STATUSES:
        raise ValueError("status is invalid")
    with connection:
        cursor = connection.execute("UPDATE meetings SET status = ? WHERE id = ?", (status, meeting_id))
    if cursor.rowcount != 1:
        raise KeyError(meeting_id)
    return get_meeting(connection, meeting_id)


def add_event(connection: Connection, meeting_id: str, employee_id: str, event_type: str, content: str) -> dict[str, Any]:
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
    return {"id": event_id, "meeting_id": meeting_id, "employee_id": employee_id, "event_type": event_type, "content": content, "created_at": created_at}


def list_events(connection: Connection, meeting_id: str) -> list[dict[str, Any]]:
    _text(meeting_id, "meeting_id", 100)
    rows = connection.execute("SELECT id, meeting_id, employee_id, event_type, content, created_at FROM meeting_events WHERE meeting_id = ? ORDER BY created_at, id", (meeting_id,)).fetchall()
    return [dict(zip(("id", "meeting_id", "employee_id", "event_type", "content", "created_at"), row)) for row in rows]


def run_dynamic_meeting(connection: Any, topic: str, participants: list[str]) -> dict[str, Any]:
    """Run a team meeting with the configured LLM provider or offline fallback text."""
    from .config import Settings
    from .employee_memory import lessons_text, remember
    from .employee_skills import load_employee_skills
    from .llm import create_llm_from_settings

    settings = Settings.from_environment()
    llm = create_llm_from_settings(settings, record_calls=True)

    from .office_events import bus as _bus

    starts_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    meeting = create_meeting(connection, topic, starts_at, participants)
    meeting_id = meeting["id"]
    set_status(connection, meeting_id, "active")
    _bus.publish({"type": "meeting", "status": "started", "meeting_id": meeting_id,
                  "task": topic, "participants": list(participants)})

    transcript = []
    warnings = []
    # Conversation turns
    for emp in participants:
        skill_text = ""
        try:
            skill_text = load_employee_skills(emp)[:1500]
        except Exception:
            pass

        lessons = lessons_text(connection, emp)
        handoff = "\n".join(
            f"{turn['employee'].title()} menyampaikan: {turn['speech']}"
            for turn in transcript
        ) or "Belum ada pendapat sebelumnya."
        prompt = (
            f"Konteks: Rapat tim kantor Loker House.\n"
            f"Topik rapat: '{topic}'.\n"
            f"Identitas Anda: Karyawan '{emp}'.\n"
            f"Pendapat rekan yang perlu ditanggapi (jika ada):\n{handoff}\n\n"
            f"Skill & peran Anda:\n{skill_text}\n\n"
            + (f"Pelajaran dari pengalaman & feedback owner sebelumnya:\n{lessons}\n\n" if lessons else "")
            +
            f"Beri tanggapan padat (1-2 kalimat) sesuai keahlian Anda mengenai topik tersebut. "
            f"Sampaikan solusi konkret, bukan basa-basi."
        )
        failure_code = None
        try:
            speech = llm.complete(
                "answer",
                [{"role": "user", "content": prompt}],
                persona=emp,
                memory_context=lessons,
                run_id=meeting_id,
                session_key=f"bot-loker-wfh:v2:employee:{emp}",
                session_id=f"loker-meeting-{meeting_id}-{emp}",
            ).text.strip() if llm else ""
            if not llm:
                failure_code = "llm_disabled"
        except Exception as error:
            failure_code = getattr(error, "code", None) or "llm_error"
            speech = ""
        if not speech:
            failure_code = failure_code or "empty_response"
            warning = f"Fallback lokal dipakai untuk {emp}; kode error Hermes: {failure_code}."
            warnings.append(warning)
            speech = f"Saya siap mendukung topik {topic} sesuai fokus tim saya."

        add_event(connection, meeting_id, emp, "note", speech)
        _bus.publish({"type": "meeting", "status": "speaking", "meeting_id": meeting_id,
                      "task": topic, "employee": emp, "content": speech})
        transcript.append({"employee": emp, "speech": speech, "source": "fallback" if failure_code else "hermes"})
        if failure_code:
            add_event(connection, meeting_id, emp, "action", warning)
            _bus.publish({"type": "meeting", "status": "degraded", "meeting_id": meeting_id,
                          "task": topic, "employee": emp, "content": warning})

    # Summary turn
    decision_prompt = (
        f"Rangkum hasil rapat tim dengan topik '{topic}'.\n"
        f"Pernyataan tim:\n"
        + "\n".join([f"- {t['employee']}: {t['speech']}" for t in transcript])
        + "\nBuatkan 1 kesimpulan keputusan aksi konkret."
    )
    decision_error_code = None
    try:
        decision = llm.complete(
            "answer",
            [{"role": "user", "content": decision_prompt}],
            persona=participants[0] if participants else "tegar",
            run_id=meeting_id,
            session_key=f"bot-loker-wfh:v2:employee:{participants[0] if participants else 'tegar'}",
            session_id=f"loker-meeting-{meeting_id}-decision",
        ).text.strip() if llm else ""
        if not llm:
            decision_error_code = "llm_disabled"
    except Exception as error:
        decision_error_code = getattr(error, "code", None) or "llm_error"
        decision = ""
    if not decision:
        decision_error_code = decision_error_code or "empty_response"
        warning = f"Fallback lokal dipakai untuk keputusan rapat; kode error Hermes: {decision_error_code}."
        warnings.append(warning)
        decision = f"Tim sepakat mengeksekusi prioritas terkait {topic}."

    add_event(connection, meeting_id, participants[0] if participants else "cora", "decision", decision)
    if decision_error_code:
        warning_employee = participants[0] if participants else "cora"
        add_event(connection, meeting_id, warning_employee, "action", warning)
        _bus.publish({"type": "meeting", "status": "degraded", "meeting_id": meeting_id,
                      "task": topic, "employee": warning_employee, "content": warning})
    for emp in participants:  # everyone in the room carries the decision into later work
        try:
            remember(connection, emp, f"Keputusan rapat '{topic[:200]}': {decision[:1500]}",
                     kind="observation", source=f"meeting:{meeting_id}", importance=0.6)
        except ValueError:  # unknown/invalid employee id from the request body
            pass
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
        "degraded": bool(warnings),
        "warnings": warnings,
    }
