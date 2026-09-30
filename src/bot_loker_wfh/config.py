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
    lead_telegram_channels: tuple[str, ...] = ()

    llm_provider: str = "template"
    ninerouter_base_url: str = "http://localhost:20128/v1"
    ninerouter_api_key: str | None = None
    ninerouter_model: str = ""
    ninerouter_fallback_models: tuple[str, ...] = ()
    llm_model_draft: str = ""
    llm_model_form: str = ""
    llm_model_answer: str = ""
    llm_timeout_seconds: float = 60.0
    llm_task_budget_seconds: float = 90.0
    llm_temperature_draft: float = 0.4

    form_engine: str = "playwright"
    browser_mcp_command: str = "npx -y @browsermcp/mcp@0.1.3"
    form_min_confidence: float = 0.7
    form_max_actions: int = 60
    form_max_tool_calls: int = 80
    form_timeout_seconds: float = 300.0
    form_ai_answers: str = "review"

    @classmethod
    def from_environment(
        cls, values: Mapping[str, str] | None = None
    ) -> "Settings":
        if values is None:
            load_dotenv()
        source = environ if values is None else values
        enabled = source.get("EXTERNAL_JOBS_ENABLED", "false").lower()

        anthropic_key = source.get("ANTHROPIC_API_KEY") or None
        llm_prov = source.get("LLM_PROVIDER")
        if not llm_prov:
            llm_prov = "anthropic" if anthropic_key else "template"

        fallback_raw = source.get("NINEROUTER_FALLBACK_MODELS", "")
        fallback_models = tuple(
            item.strip() for item in fallback_raw.split(",") if item.strip()
        )

        return cls(
            environment=source.get("APP_ENV", "development"),
            database_url=source.get("DATABASE_URL", "sqlite:///data/app.db"),
            external_jobs_enabled=enabled in {"1", "true", "yes", "on"},
            telegram_bot_token=source.get("TELEGRAM_BOT_TOKEN") or None,
            telegram_allowed_chat_ids=_parse_chat_ids(
                source.get("TELEGRAM_ALLOWED_CHAT_IDS", "")
            ),
            profile_path=source.get("PROFILE_PATH") or "data/profile.json",
            anthropic_api_key=anthropic_key,
            anthropic_model=source.get("ANTHROPIC_MODEL") or "claude-sonnet-5",
            fetch_interval_hours=float(source.get("FETCH_INTERVAL_HOURS") or 4),
            form_assist_enabled=source.get("FORM_ASSIST_ENABLED", "false").lower()
            in {"1", "true", "yes", "on"},
            applicant_path=source.get("APPLICANT_PATH") or "data/applicant.json",
            answers_path=source.get("ANSWERS_PATH") or "data/answers.json",
            lead_telegram_channels=tuple(
                item.strip()
                for item in source.get("LEAD_TELEGRAM_CHANNELS", "").split(",")
                if item.strip()
            ),
            llm_provider=llm_prov,
            ninerouter_base_url=source.get(
                "NINEROUTER_BASE_URL", "http://localhost:20128/v1"
            ),
            ninerouter_api_key=source.get("NINEROUTER_API_KEY") or None,
            ninerouter_model=source.get("NINEROUTER_MODEL", ""),
            ninerouter_fallback_models=fallback_models,
            llm_model_draft=source.get("LLM_MODEL_DRAFT", ""),
            llm_model_form=source.get("LLM_MODEL_FORM", ""),
            llm_model_answer=source.get("LLM_MODEL_ANSWER", ""),
            llm_timeout_seconds=float(source.get("LLM_TIMEOUT_SECONDS") or 60.0),
            llm_task_budget_seconds=float(
                source.get("LLM_TASK_BUDGET_SECONDS") or 90.0
            ),
            llm_temperature_draft=float(
                source.get("LLM_TEMPERATURE_DRAFT") or 0.4
            ),
            form_engine=source.get("FORM_ENGINE", "playwright"),
            browser_mcp_command=source.get(
                "BROWSER_MCP_COMMAND", "npx -y @browsermcp/mcp@0.1.3"
            ),
            form_min_confidence=float(source.get("FORM_MIN_CONFIDENCE") or 0.7),
            form_max_actions=int(source.get("FORM_MAX_ACTIONS") or 60),
            form_max_tool_calls=int(source.get("FORM_MAX_TOOL_CALLS") or 80),
            form_timeout_seconds=float(source.get("FORM_TIMEOUT_SECONDS") or 300.0),
            form_ai_answers=source.get("FORM_AI_ANSWERS", "review"),
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
