"""Retention cleanup for filtered-out jobs."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone


class FilteredOutRetention:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        now: datetime | None = None,
        retention_days: int = 90,
    ) -> None:
        if retention_days < 0:
            raise ValueError("retention_days cannot be negative")
        self.connection = connection
        self.now = _as_utc(now or datetime.now(timezone.utc))
        self.retention_days = retention_days

    def cleanup(self) -> int:
        cutoff = (self.now - timedelta(days=self.retention_days)).isoformat()
        cursor = self.connection.execute(
            "DELETE FROM jobs "
            "WHERE status = 'FILTERED_OUT' "
            "AND fetched_at < ? "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM applications WHERE applications.job_id = jobs.id"
            ")",
            (cutoff,),
        )
        self.connection.commit()
        return cursor.rowcount


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

