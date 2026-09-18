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
    telegram_bot_token: str | None
    telegram_allowed_chat_ids: frozenset[int]

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
            telegram_bot_token=source.get("TELEGRAM_BOT_TOKEN") or None,
            telegram_allowed_chat_ids=_parse_chat_ids(
                source.get("TELEGRAM_ALLOWED_CHAT_IDS", "")
            ),
        )


def _parse_chat_ids(value: str) -> frozenset[int]:
    chat_ids: set[int] = set()
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        chat_ids.add(int(item))
    return frozenset(chat_ids)
