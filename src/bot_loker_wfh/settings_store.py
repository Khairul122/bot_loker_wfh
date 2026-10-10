"""Application settings: authoritative Supabase store plus a local SQLite cache.

The scrape interval and the office panel's runtime-tunable values live here so
the owner can change them without restarting the bot. When Supabase is
configured it is the source of truth: the office server reads and writes the
cloud `app_settings` table and only then refreshes the local cache (`app_settings`
in SQLite) and the process environment. When Supabase is not configured the bot
runs fully offline against the local cache.
"""

from __future__ import annotations

import sqlite3

from . import database


# Key -> (default, lower bound). None lower bound means "no minimum".
DEFAULTS: dict[str, tuple[str, float | None]] = {
    "scrape_interval_hours": ("4", 0.08),  # 5 minutes
}

# Supabase table mirrored by the local app_settings rows.
CLOUD_TABLE = "app_settings"


class SupabaseUnavailable(RuntimeError):
    """Raised when the Supabase settings backend cannot be reached."""


def cloud_error_types() -> tuple[type[BaseException], ...]:
    """Exception classes that mean "the cloud settings backend is down".

    Includes the one database.py defines once its Supabase layer lands, so the
    office server can map either to an HTTP 503.
    """
    types: list[type[BaseException]] = [SupabaseUnavailable]
    remote = getattr(database, "SupabaseUnavailable", None)
    if isinstance(remote, type) and remote not in types:
        types.append(remote)
    return tuple(types)


def cloud_configured() -> bool:
    """True when database.py has a configured Supabase backend."""
    configured = getattr(database, "supabase_configured", None)
    return bool(configured()) if callable(configured) else False


def _request(**kwargs):
    request = getattr(database, "supabase_request", None)
    if not callable(request):
        raise SupabaseUnavailable("supabase integration unavailable")
    return request(CLOUD_TABLE, **kwargs)


def fetch_cloud_settings() -> dict[str, str]:
    """All key/value rows from Supabase. Raises when the backend is unreachable."""
    rows = _request(method="GET", query={"select": "key,value"}) or []
    result: dict[str, str] = {}
    for row in rows:
        key = row.get("key") if isinstance(row, dict) else None
        if key is not None:
            result[str(key)] = str(row.get("value", ""))
    return result


def store_cloud_setting(key: str, value: str) -> None:
    """Upsert one setting in Supabase (authoritative). Raises on failure."""
    _request(method="POST", data={"key": key, "value": value}, prefer="resolution=merge-duplicates")


def get_setting(connection: sqlite3.Connection, key: str) -> str:
    default, _ = DEFAULTS[key]
    row = connection.execute(
        "SELECT value FROM app_settings WHERE key = ?", (key,)
    ).fetchone()
    return row[0] if row else default


def set_setting(connection: sqlite3.Connection, key: str, value: str) -> None:
    _, lower = DEFAULTS[key]
    if lower is not None and float(value) < lower:
        raise ValueError(f"{key} must be >= {lower} hours")
    connection.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
        "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')",
        (key, value),
    )
    connection.commit()


def get_scrape_interval_hours(connection: sqlite3.Connection) -> float:
    return float(get_setting(connection, "scrape_interval_hours"))


def set_scrape_interval_hours(connection: sqlite3.Connection, hours: float) -> None:
    set_setting(connection, "scrape_interval_hours", str(hours))
