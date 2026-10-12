"""Internal division task assignment and review; never submits external work."""

from __future__ import annotations

from uuid import uuid4

from .company import EMPLOYEES, division_for_employee, managed_division_for
from .database import Connection

PRIORITIES = frozenset({"low", "normal", "high"})
STATUSES = frozenset({"assigned", "in_progress", "reviewed"})


def _manager_division(manager: str) -> dict:
    division = managed_division_for(manager)
    if division is None:
        raise KeyError(manager)
    return division


def list_tasks(connection: Connection, manager: str) -> list[dict]:
    division = _manager_division(manager)
    rows = connection.execute(
        """SELECT id, assignee, title, priority, status, review_note, created_at, updated_at
           FROM office_manager_tasks WHERE division = ? ORDER BY
           CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END,
           updated_at DESC""",
        (division["id"],),
    ).fetchall()
    names = {employee["id"]: employee["name"] for employee in EMPLOYEES}
    return [
        {
            "id": row["id"],
            "assignee": row["assignee"],
            "assignee_name": names.get(row["assignee"], row["assignee"]),
            "title": row["title"],
            "priority": row["priority"],
            "status": row["status"],
            "review_note": row["review_note"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def create_task(connection: Connection, manager: str, assignee: str, title: str, priority: str = "normal") -> dict:
    division = _manager_division(manager)
    employee_division = division_for_employee(assignee)
    if employee_division is None or employee_division["id"] != division["id"]:
        raise ValueError("assignee_must_be_in_managed_division")
    clean_title = " ".join(str(title).split())
    if not 3 <= len(clean_title) <= 160:
        raise ValueError("invalid_title")
    if priority not in PRIORITIES:
        raise ValueError("invalid_priority")
    task_id = uuid4().hex
    with connection:
        connection.execute(
            """INSERT INTO office_manager_tasks (id, division, manager, assignee, title, priority)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (task_id, division["id"], manager, assignee, clean_title, priority),
        )
    return {"id": task_id, "division": division["id"], "manager": manager, "assignee": assignee,
            "title": clean_title, "priority": priority, "status": "assigned", "review_note": ""}


def update_task(connection: Connection, manager: str, task_id: str, status: str, review_note: str = "") -> dict:
    division = _manager_division(manager)
    if status not in STATUSES:
        raise ValueError("invalid_status")
    note = " ".join(str(review_note).split())
    if len(note) > 500:
        raise ValueError("invalid_review_note")
    with connection:
        row = connection.execute(
            """UPDATE office_manager_tasks SET status = ?, review_note = ?, updated_at = utc_now_iso()
               WHERE id = ? AND division = ? RETURNING id, assignee, title, priority, status, review_note""",
            (status, note, task_id, division["id"]),
        ).fetchone()
    if row is None:
        raise KeyError(task_id)
    return {key: row[key] for key in ("id", "assignee", "title", "priority", "status", "review_note")}
