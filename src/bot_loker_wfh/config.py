"""Environment-backed application settings."""

from __future__ import annotations

from dataclasses import dataclass
from os import environ
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class Settings:
    environment: str
    database_url: str
    external_jobs_enabled: bool
    telegram_bot_token: str | None
    telegram_allowed_chat_ids: frozenset[int]
    profile_path: str = "data/profile.json"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    fetch_interval_hours: float = 4.0
    form_assist_enabled: bool = False
    applicant_path: str = "data/applicant.json"
    answers_path: str = "data/answers.json"

    @classmethod
    def from_environment(
        cls, values: Mapping[str, str] | None = None
    ) -> "Settings":
        if values is None:
            load_dotenv()
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
            profile_path=source.get("PROFILE_PATH") or "data/profile.json",
            anthropic_api_key=source.get("ANTHROPIC_API_KEY") or None,
            anthropic_model=source.get("ANTHROPIC_MODEL") or "claude-sonnet-5",
            fetch_interval_hours=float(source.get("FETCH_INTERVAL_HOURS") or 4),
            form_assist_enabled=source.get("FORM_ASSIST_ENABLED", "false").lower()
            in {"1", "true", "yes", "on"},
            applicant_path=source.get("APPLICANT_PATH") or "data/applicant.json",
            answers_path=source.get("ANSWERS_PATH") or "data/answers.json",
        )


def load_dotenv(path: str | Path = ".env") -> None:
    """Load KEY=VALUE lines into the process environment.

    Variables that are already set are never overridden, so a real shell
    environment always wins over the file.
    """
    env_path = Path(path)
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key:
            environ.setdefault(key, value)


def _parse_chat_ids(value: str) -> frozenset[int]:
    chat_ids: set[int] = set()
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        chat_ids.add(int(item))
    return frozenset(chat_ids)
