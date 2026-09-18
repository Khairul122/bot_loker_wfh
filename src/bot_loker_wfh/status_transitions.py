"""Centralized job and application status transitions."""

from __future__ import annotations

import sqlite3
import uuid
from enum import StrEnum


class TransitionActor(StrEnum):
    SYSTEM = "system"
    USER = "user"


class InvalidTransitionError(ValueError):
    """Raised when a status transition is not allowed."""


JOB_TRANSITIONS = {
    "DISCOVERED": {"CANDIDATE", "FILTERED_OUT"},
}

APPLICATION_TRANSITIONS = {
    "DRAFT_READY": {"PENDING_APPROVAL"},
    "PENDING_APPROVAL": {"APPROVED", "REJECTED_BY_USER", "WITHDRAWN"},
    "APPROVED": {"SUBMITTING", "WITHDRAWN"},
    "SUBMITTING": {"SUBMITTED", "SUBMIT_FAILED", "SUBMISSION_AMBIGUOUS"},
    "SUBMIT_FAILED": {"APPROVED"},
    "SUBMISSION_AMBIGUOUS": {"SUBMITTED", "SUBMIT_FAILED", "APPROVED"},
    "SUBMITTED": {"VIEWED", "INTERVIEW", "REJECTED_BY_COMPANY", "NO_RESPONSE"},
    "VIEWED": {"INTERVIEW", "REJECTED_BY_COMPANY", "NO_RESPONSE"},
    "INTERVIEW": {"OFFER", "REJECTED_BY_COMPANY"},
}


def transition_job_status(
    connection: sqlite3.Connection,
    *,
    job_id: str,
    to_status: str,
    actor: TransitionActor,
    manual_correction: bool = False,
    reason: str | None = None,
) -> None:
    del actor
    from_status = _fetch_status(connection, table="jobs", row_id=job_id)
    if not manual_correction:
        _validate_transition(
            kind="job",
            transitions=JOB_TRANSITIONS,
            from_status=from_status,
            to_status=to_status,
        )
    else:
        _validate_manual_correction(reason)

    connection.execute(
        "UPDATE jobs SET status = ? WHERE id = ?",
        (to_status, job_id),
    )
    connection.commit()


def transition_application_status(
    connection: sqlite3.Connection,
    *,
    application_id: str,
    to_status: str,
    actor: TransitionActor,
    manual_correction: bool = False,
    reason: str | None = None,
) -> None:
    from_status = _fetch_status(
        connection, table="applications", row_id=application_id
    )
    if not manual_correction:
        _validate_transition(
            kind="application",
            transitions=APPLICATION_TRANSITIONS,
            from_status=from_status,
            to_status=to_status,
        )
    else:
        _validate_manual_correction(reason)

    connection.execute(
        "UPDATE applications SET status = ? WHERE id = ?",
        (to_status, application_id),
    )
    connection.execute(
        "INSERT INTO application_status_history "
        "(id, application_id, from_status, to_status, changed_by) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), application_id, from_status, to_status, actor.value),
    )
    connection.commit()


def _fetch_status(
    connection: sqlite3.Connection, *, table: str, row_id: str
) -> str:
    row = connection.execute(
        f"SELECT status FROM {table} WHERE id = ?",
        (row_id,),
    ).fetchone()
    if row is None:
        raise InvalidTransitionError(f"Unknown {table[:-1]} id: {row_id}")
    return row[0]


def _validate_transition(
    *,
    kind: str,
    transitions: dict[str, set[str]],
    from_status: str,
    to_status: str,
) -> None:
    allowed = transitions.get(from_status, set())
    if to_status not in allowed:
        raise InvalidTransitionError(
            f"Invalid {kind} transition: {from_status} -> {to_status}"
        )


def _validate_manual_correction(reason: str | None) -> None:
    if not reason or not reason.strip():
        raise InvalidTransitionError("Manual correction requires a reason")
