"""Environment-backed application settings."""

from __future__ import annotations

from dataclasses import dataclass
from os import environ
from typing import Mapping


@dataclass(frozen=True)
class Settings:
    environment: str
    database_url: str
    external_jobs_enabled: bool

    @classmethod
    def from_environment(
        cls, values: Mapping[str, str] | None = None
    ) -> "Settings":
        source = environ if values is None else values
        enabled = source.get("EXTERNAL_JOBS_ENABLED", "false").lower()

        return cls(
            environment=source.get("APP_ENV", "development"),
            database_url=source.get("DATABASE_URL", "sqlite:///data/app.db"),
            external_jobs_enabled=enabled in {"1", "true", "yes", "on"},
        )

