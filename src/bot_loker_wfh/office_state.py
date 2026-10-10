"""Validated durable state for 3D office characters (Supabase Postgres)."""

from __future__ import annotations

import math
from collections.abc import Mapping

from .database import Connection


_MAX_COORDINATE = 10000.0


def _position(value: Mapping, *, character_id: str) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise ValueError(f"invalid position for {character_id}")
    result = {}
    for key in ("x", "y", "z"):
        number = value.get(key)
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
            raise ValueError(f"invalid position for {character_id}")
        if abs(float(number)) > _MAX_COORDINATE:
            raise ValueError(f"invalid position for {character_id}")
        result[key] = float(number)
    yaw = value.get("yaw", 0)
    if isinstance(yaw, bool) or not isinstance(yaw, (int, float)) or not math.isfinite(yaw):
        raise ValueError(f"invalid position for {character_id}")
    result["yaw"] = float(yaw)
    return result


def _state_input(state: Mapping) -> list[tuple[str, str, dict[str, float]]]:
    if not isinstance(state, Mapping):
        raise ValueError("state must be an object")
    rows: list[tuple[str, str, dict[str, float]]] = []
    owner = state.get("owner")
    if owner is not None:
        rows.append(("owner", "owner", _position(owner, character_id="owner")))
    staff = state.get("staff", {})
    if not isinstance(staff, Mapping):
        raise ValueError("staff must be an object")
    for character_id, value in staff.items():
        if not isinstance(character_id, str) or not character_id or len(character_id) > 100:
            raise ValueError("invalid character id")
        rows.append((character_id, "staff", _position(value, character_id=character_id)))
    return rows


def _rows_to_state(rows) -> dict:
    owner = None
    staff = {}
    for row in rows:
        value = {"x": float(row["x"]), "y": float(row["y"]), "z": float(row["z"]), "yaw": float(row["yaw"])}
        if row["role"] == "owner":
            owner = value
        else:
            staff[row["character_id"]] = value
    return {"owner": owner, "staff": staff}


def load_state(connection: Connection) -> dict:
    rows = connection.execute(
        "SELECT character_id, role, x, y, z, yaw FROM office_character_state ORDER BY character_id"
    ).fetchall()
    return _rows_to_state(rows)


def save_state(connection: Connection, state: Mapping) -> dict:
    rows = _state_input(state)
    with connection:
        connection.executemany(
            "INSERT INTO office_character_state (character_id, role, x, y, z, yaw) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(character_id) DO UPDATE SET role=excluded.role, x=excluded.x, "
            "y=excluded.y, z=excluded.z, yaw=excluded.yaw, updated_at=utc_now_iso()",
            [(cid, role, p["x"], p["y"], p["z"], p["yaw"]) for cid, role, p in rows],
        )
    return load_state(connection)


load_character_state = load_state
save_character_state = save_state
