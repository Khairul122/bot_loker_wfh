"""Internal division task assignment and review; never submits external work."""

from __future__ import annotations

import json
from uuid import uuid4

from .company import EMPLOYEES, division_for_employee, managed_division_for
from .database import Connection

PRIORITIES = frozenset({"low", "normal", "high"})
STATUSES = frozenset({"assigned", "in_progress", "reviewed"})
MAX_BRIEF_TASKS = 3


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


def assign_recommendations(connection: Connection, manager: str, recommendations: list[dict]) -> list[dict]:
    """Record the manager's validated Hermes recommendations as internal team assignments."""
    division = _manager_division(manager)
    if not isinstance(recommendations, list) or len(recommendations) > MAX_BRIEF_TASKS:
        raise ValueError("invalid_recommendations")
    members = {employee["id"]: employee["name"] for employee in EMPLOYEES
               if employee["division"] == division["id"]}
    existing_titles = {task["title"].casefold() for task in list_tasks(connection, manager)
                       if task["status"] != "reviewed"}
    validated = []
    for recommendation in recommendations:
        if not isinstance(recommendation, dict):
            raise ValueError("invalid_recommendations")
        assignee = recommendation.get("assignee")
        title = " ".join(str(recommendation.get("title") or "").split())
        priority = recommendation.get("priority")
        if not isinstance(assignee, str) or assignee not in members or not 3 <= len(title) <= 160:
            raise ValueError("invalid_recommendations")
        if not isinstance(priority, str) or priority not in PRIORITIES:
            raise ValueError("invalid_recommendations")
        if title.casefold() in existing_titles:
            continue
        existing_titles.add(title.casefold())
        validated.append({"id": uuid4().hex, "division": division["id"], "manager": manager,
                          "assignee": assignee, "assignee_name": members[assignee], "title": title,
                          "priority": priority, "status": "assigned", "review_note": ""})
    with connection:
        connection.executemany(
            """INSERT INTO office_manager_tasks (id, division, manager, assignee, title, priority)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [(task["id"], task["division"], manager, task["assignee"], task["title"], task["priority"])
             for task in validated],
        )
    return validated


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


def division_brief(connection: Connection, manager: str, llm) -> dict:
    """Ask the division's Hermes manager to assess real aggregate metrics and suggest internal work."""
    division = _manager_division(manager)
    if llm is None:
        raise RuntimeError("hermes_unavailable")

    from . import office_desk
    from .employee_memory import lessons_text

    instruction = office_desk.get_instruction(connection, manager)
    lessons = lessons_text(connection, manager)
    memory = "\n".join(part for part in (instruction, lessons) if part)
    runner = getattr(llm, "router", None) or llm
    chain = getattr(runner, "chain", ())
    if chain:
        provider = chain[0][0]
        readiness_check = getattr(provider, "check_readiness", None)
        if not callable(readiness_check):
            raise RuntimeError("hermes_not_ready")
        model = getattr(runner, "task_models", {}).get("manager")
        readiness = readiness_check(required_models=(model,) if model else ())
        if not readiness.get("ok"):
            raise RuntimeError("hermes_not_ready")
    context = {
        "persona": manager,
        "memory_context": memory,
        "session_key": f"loker:manager:{division['id']}",
        "session_id": f"loker-manager-brief-{division['id']}",
        "system_prompt": (
            f"You are the accountable manager for the {division['name']} division. "
            "Review team performance, set internal priorities, and propose bounded assignments. "
            "You may recommend only internal work for this division. Never submit applications or bids, "
            "contact third parties, change application states, or bypass CAPTCHA. Owner approval remains "
            "mandatory for every external action. Use only the supplied aggregate data; do not invent facts."
        ),
    }
    if hasattr(runner, "for_task"):
        agent = runner.for_task("manager", **context)
    elif hasattr(runner, "with_context"):
        agent = runner.with_context(**context)
    else:
        agent = runner

    team = []
    for employee in EMPLOYEES:
        if employee["division"] != division["id"]:
            continue
        measured = office_desk.measure(connection, employee["id"], 24)
        team.append({
            "id": employee["id"],
            "name": employee["name"],
            "role": employee["responsibility"],
            "metrics": measured["metrics"],
            "activity": measured["lines"],
        })
    open_tasks = [task for task in list_tasks(connection, manager) if task["status"] != "reviewed"]
    prompt = (
        "Buat brief manajer divisi dalam Bahasa Indonesia berdasarkan JSON konteks berikut. "
        "Balas hanya JSON valid dengan bentuk: {\"summary\": string, \"priorities\": "
        "[{\"title\": string, \"assignee\": employee_id, \"priority\": \"low|normal|high\", "
        "\"reason\": string}]}. Maksimal 3 prioritas. Pilih assignee dari anggota divisi saja. "
        "Jika tidak ada tindakan yang layak, priorities boleh kosong. Ringkasan maks 500 karakter, "
        "judul 3-160 karakter, alasan maks 300 karakter. Jangan membuat tugas eksternal.\n\n"
        + json.dumps({"division": division["name"], "manager": manager, "team_24h": team,
                      "open_internal_tasks": open_tasks}, ensure_ascii=False)
    )
    text = str(agent(prompt) or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].lstrip()
    try:
        result = json.loads(text)
    except (TypeError, ValueError) as error:
        raise ValueError("invalid_manager_brief") from error
    if not isinstance(result, dict) or not isinstance(result.get("summary"), str):
        raise ValueError("invalid_manager_brief")
    summary = " ".join(result["summary"].split())
    if not 1 <= len(summary) <= 500:
        raise ValueError("invalid_manager_brief")
    priorities = result.get("priorities")
    if not isinstance(priorities, list) or len(priorities) > MAX_BRIEF_TASKS:
        raise ValueError("invalid_manager_brief")
    allowed_assignees = {member["id"] for member in EMPLOYEES if member["division"] == division["id"]}
    validated = []
    for item in priorities:
        if not isinstance(item, dict):
            raise ValueError("invalid_manager_brief")
        title = " ".join(str(item.get("title") or "").split())
        assignee = item.get("assignee")
        priority = item.get("priority")
        reason = " ".join(str(item.get("reason") or "").split())
        if not 3 <= len(title) <= 160 or not isinstance(assignee, str) or assignee not in allowed_assignees:
            raise ValueError("invalid_manager_brief")
        if not isinstance(priority, str) or priority not in PRIORITIES or len(reason) > 300:
            raise ValueError("invalid_manager_brief")
        employee_name = next(member["name"] for member in EMPLOYEES if member["id"] == assignee)
        validated.append({"title": title, "assignee": assignee, "assignee_name": employee_name,
                          "priority": priority, "reason": reason})
    return {"division": {"id": division["id"], "name": division["name"], "manager": manager},
            "summary": summary, "priorities": validated}
