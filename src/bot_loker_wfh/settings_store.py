"""Persistent application settings stored in SQLite (table `app_settings`).

The scrape interval lives here (not in the environment) so the owner can tune
it at runtime from the office dashboard or Telegram without restarting.
"""

from __future__ import annotations

import sqlite3


# Key -> (default, lower bound). None lower bound means "no minimum".
DEFAULTS: dict[str, tuple[str, float | None]] = {
    "scrape_interval_hours": ("4", 0.08),  # 5 minutes
}


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
