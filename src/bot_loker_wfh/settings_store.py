"""Application settings stored in the Supabase `app_settings` table.

The scrape interval and the office panel's runtime-tunable values live here so the owner can
change them without restarting the bot.
"""

from __future__ import annotations

from .database import Connection


# Key -> (default, lower bound). None lower bound means "no minimum".
DEFAULTS: dict[str, tuple[str, float | None]] = {
    "scrape_interval_hours": ("4", 0.08),  # 5 minutes
    # hands-off freelance bidding (see auto_bid.py); off until the owner switches it on
    "auto_bid_enabled": ("0", None),
    "auto_bid_max_per_day": ("5", 1),
    "auto_bid_min_score": ("0.7", 0),
    "auto_bid_max_competitors": ("40", 1),
    "auto_bid_max_age_hours": ("24", 1),
}


def all_settings(connection: Connection) -> dict[str, str]:
    """Every stored key/value pair."""
    return {str(key): str(value) for key, value in connection.execute("SELECT key, value FROM app_settings")}


def get_setting(connection: Connection, key: str) -> str:
    default = DEFAULTS[key][0] if key in DEFAULTS else ""
    row = connection.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(connection: Connection, key: str, value: str) -> None:
    lower = DEFAULTS[key][1] if key in DEFAULTS else None
    if lower is not None and float(value) < lower:
        raise ValueError(f"{key} must be >= {lower} hours")
    connection.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
        "updated_at = utc_now_iso()",
        (key, value),
    )
    connection.commit()


def get_scrape_interval_hours(connection: Connection) -> float:
    return float(get_setting(connection, "scrape_interval_hours"))


def set_scrape_interval_hours(connection: Connection, hours: float) -> None:
    set_setting(connection, "scrape_interval_hours", str(hours))
