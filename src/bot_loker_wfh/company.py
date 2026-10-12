"""Canonical employee and division catalog shared with the office UI."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_CATALOG_PATH = Path(__file__).with_name("office") / "company.json"
_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def _load_catalog() -> dict[str, Any]:
    data = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    divisions = data.get("divisions")
    employees = data.get("employees")
    max_floors = data.get("max_floors")
    if not isinstance(max_floors, int) or not 1 <= max_floors <= 7:
        raise ValueError("company catalog max_floors must be between 1 and 7")
    if not isinstance(divisions, list) or not divisions or len(divisions) > max_floors:
        raise ValueError("company catalog must fit its divisions within max_floors")
    if not isinstance(employees, list) or not employees:
        raise ValueError("company catalog must contain employees")

    division_ids = [item.get("id") for item in divisions]
    employee_ids = [item.get("id") for item in employees]
    if any(not isinstance(value, str) or not _ID_RE.fullmatch(value) for value in division_ids + employee_ids):
        raise ValueError("company catalog contains an invalid id")
    if len(set(division_ids)) != len(division_ids) or len(set(employee_ids)) != len(employee_ids):
        raise ValueError("company catalog ids must be unique")

    floors = [item.get("floor") for item in divisions]
    if any(not isinstance(floor, int) or floor < 0 or floor >= max_floors for floor in floors):
        raise ValueError("company catalog contains a floor outside max_floors")
    if sorted(floors) != list(range(len(divisions))):
        raise ValueError("division floors must be contiguous and start at zero")

    employee_by_id = {employee["id"]: employee for employee in employees}
    managers = [division.get("manager") for division in divisions]
    if any(manager not in employee_by_id for manager in managers) or len(set(managers)) != len(managers):
        raise ValueError("each division must have one unique employee manager")
    if any(employee.get("division") not in division_ids for employee in employees):
        raise ValueError("each employee must belong to a known division")
    if any(not isinstance(employee.get("responsibility"), str) or not employee["responsibility"].strip() for employee in employees):
        raise ValueError("each employee must have a responsibility")
    for division in divisions:
        if employee_by_id[division["manager"]]["division"] != division["id"]:
            raise ValueError("a division manager must belong to their division")
    for employee in employees:
        employee["is_manager"] = employee["id"] in managers
    return data


_CATALOG = _load_catalog()
MAX_FLOORS: int = _CATALOG["max_floors"]
DIVISIONS: tuple[dict[str, Any], ...] = tuple(_CATALOG["divisions"])
EMPLOYEES: tuple[dict[str, Any], ...] = tuple(_CATALOG["employees"])
ROLES: dict[str, str] = {employee["id"]: employee["responsibility"] for employee in EMPLOYEES}
MANAGERS: dict[str, str] = {division["id"]: division["manager"] for division in DIVISIONS}
JOB_SCOUTS: dict[str, str] = {
    employee["id"]: employee["source"] for employee in EMPLOYEES if employee.get("pipeline") == "jobs"
}
LEAD_SCOUTS: dict[str, str] = {
    employee["id"]: employee["source"] for employee in EMPLOYEES if employee.get("pipeline") == "leads"
}
_DIVISION_BY_EMPLOYEE = {employee["id"]: next(d for d in DIVISIONS if d["id"] == employee["division"]) for employee in EMPLOYEES}


def division_for_employee(employee_id: str) -> dict[str, Any] | None:
    """Return the employee's division, or None when the id is unknown."""
    return _DIVISION_BY_EMPLOYEE.get(employee_id)


def managed_division_for(employee_id: str) -> dict[str, Any] | None:
    """Return the division only when this employee is its approved manager."""
    division = division_for_employee(employee_id)
    if division and division["manager"] == employee_id:
        return division
    return None
