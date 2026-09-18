"""Structured, privacy-safe application logging."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any


ALLOWED_FIELDS = frozenset(
    {
        "event",
        "run_id",
        "entry_point",
        "job_id",
        "application_id",
        "source",
        "status",
        "duration_ms",
        "inserted_count",
        "error_code",
        "attempt",
    }
)


class StructuredLogger:
    def __init__(self, logger: logging.Logger, *, run_id: str | None = None):
        self.logger = logger
        self.run_id = run_id or str(uuid.uuid4())

    def event(self, event: str, **fields: Any) -> None:
        self._write(logging.INFO, event, fields)

    def error(self, event: str, **fields: Any) -> None:
        self._write(logging.ERROR, event, fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._write(logging.WARNING, event, fields)

    def _write(self, level: int, event: str, fields: dict[str, Any]) -> None:
        record: dict[str, Any] = {
            "event": event,
            "run_id": self.run_id,
        }
        for key, value in fields.items():
            if key not in ALLOWED_FIELDS or key in {"event", "run_id"}:
                continue
            if key == "error_code":
                record[key] = str(value) if value is not None else None
            else:
                record[key] = value
        self.logger.log(level, json.dumps(record, sort_keys=True))


def sanitize_error(error: BaseException) -> str:
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, (ConnectionError, OSError)):
        return "network_error"
    if isinstance(error, ValueError):
        return "invalid_value"
    return "unexpected_error"
