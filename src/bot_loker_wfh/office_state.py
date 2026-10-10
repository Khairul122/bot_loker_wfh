"""Validated durable state for 3D office characters (sqlite + Supabase cloud)."""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Mapping

from .database import SupabaseUnavailable, supabase_configured, supabase_request


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


def load_state(connection: sqlite3.Connection) -> dict:
    cursor = connection.execute(
        "SELECT character_id, role, x, y, z, yaw FROM office_character_state ORDER BY character_id"
    )
    columns = [description[0] for description in cursor.description]
    return _rows_to_state([dict(zip(columns, row)) for row in cursor.fetchall()])


def load_state_cloud(connection: sqlite3.Connection) -> dict:
    """Cloud-authoritative read: last position saved in Supabase, else the local cache."""
    if supabase_configured():
        try:
            rows = supabase_request(
                "office_character_state",
                query={"select": "character_id,role,x,y,z,yaw", "order": "character_id"},
            )
            if rows:
                return _rows_to_state(rows)
        except SupabaseUnavailable:
            pass
    return load_state(connection)


def _state_rows(state: Mapping) -> list[dict]:
    return [
        {"character_id": character_id, "role": role,
         "x": position["x"], "y": position["y"], "z": position["z"], "yaw": position["yaw"]}
        for character_id, role, position in _state_input(state)
    ]


def save_state(connection: sqlite3.Connection, state: Mapping) -> dict:
    rows = _state_input(state)
    with connection:
        for character_id, role, position in rows:
            connection.execute(
                "INSERT INTO office_character_state "
                "(character_id, role, x, y, z, yaw) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(character_id) DO UPDATE SET role=excluded.role, x=excluded.x, "
                "y=excluded.y, z=excluded.z, yaw=excluded.yaw, "
                "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')",
                (character_id, role, position["x"], position["y"], position["z"], position["yaw"]),
            )
    if supabase_configured():
        try:
            supabase_request(
                "office_character_state", method="POST", data=_state_rows(state),
                prefer="resolution=merge-duplicates",
            )
        except SupabaseUnavailable:
            pass
    return load_state(connection)


load_character_state = load_state
save_character_state = save_state
