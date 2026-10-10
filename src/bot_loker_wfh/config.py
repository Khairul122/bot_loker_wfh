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

    llm_provider: str = "9router"
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
    opencode_command: str = "opencode"
    opencode_model: str = "9router/ComboOpenCode"

    form_engine: str = "playwright"
    browser_mcp_command: str = "npx -y @browsermcp/mcp@0.1.3"
    github_username: str = ""
    playwright_mcp_command: str = (
        "npx -y @playwright/mcp@0.0.80 --extension --output-dir data/playwright-mcp"
    )
    form_min_confidence: float = 0.7
    form_max_actions: int = 60
    form_max_tool_calls: int = 80
    form_timeout_seconds: float = 300.0
    form_connect_timeout_seconds: float = 20.0
    form_ai_answers: str = "review"

    @classmethod
    def from_environment(
        cls, values: Mapping[str, str] | None = None
    ) -> "Settings":
        if values is None:
            load_dotenv()
        source = environ if values is None else values
        enabled = source.get("EXTERNAL_JOBS_ENABLED", "false").lower()

        llm_prov = source.get("LLM_PROVIDER") or "9router"

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
            opencode_command=source.get("OPENCODE_COMMAND") or "opencode",
            opencode_model=source.get("OPENCODE_MODEL") or "9router/ComboOpenCode",
            form_engine=source.get("FORM_ENGINE", "playwright"),
            browser_mcp_command=source.get(
                "BROWSER_MCP_COMMAND", "npx -y @browsermcp/mcp@0.1.3"
            ),
            github_username=(source.get("GITHUB_USERNAME") or "").strip(),
            playwright_mcp_command=source.get(
                "PLAYWRIGHT_MCP_COMMAND",
                "npx -y @playwright/mcp@0.0.80 --extension --output-dir data/playwright-mcp",
            ),
            form_min_confidence=float(source.get("FORM_MIN_CONFIDENCE") or 0.7),
            form_max_actions=int(source.get("FORM_MAX_ACTIONS") or 60),
            form_max_tool_calls=int(source.get("FORM_MAX_TOOL_CALLS") or 80),
            form_timeout_seconds=float(source.get("FORM_TIMEOUT_SECONDS") or 300.0),
            form_connect_timeout_seconds=float(source.get("FORM_CONNECT_TIMEOUT_SECONDS") or 20.0),
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


def save_dotenv(settings: dict, path: str | Path = ".env") -> None:
    """Save settings to .env file, preserving order/comments/blank lines."""
    env_path = Path(path)
    lines: list[str] = []
    key_to_index: dict[str, int] = {}
    if env_path.is_file():
        raw_lines = env_path.read_text(encoding="utf-8-sig").splitlines()
        for idx, raw in enumerate(raw_lines):
            lines.append(raw)
            stripped = raw.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            k, _, v = stripped.partition("=")
            k = k.strip()
            if k:
                key_to_index[k] = idx

    # ponytail: full .env parser with export/inline comments is heavier; upgrade when needed
    for key, value in settings.items():
        if value is None:
            continue
        str_value = str(value)
        # escape double quotes and wrap when needed
        needs_quote = " " in str_value or any(c in str_value for c in '#$&*()[]{}|;\'<>`~"')
        if needs_quote:
            str_value = '"' + str_value.replace('"', '\\"') + '"'
        new_line = f"{key}={str_value}"
        if key in key_to_index:
            lines[key_to_index[key]] = new_line
        else:
            # keep blank line before new keys if file doesn't end with one
            lines.append(new_line)
            key_to_index[key] = len(lines) - 1
        # keep process env in sync so Settings.from_environment() sees it without restart
        if str_value == "":
            environ.pop(key, None)
        else:
            # strip quotes for environ
            env_val = str(value)
            environ[key] = env_val

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_chat_ids(value: str) -> frozenset[int]:
    chat_ids: set[int] = set()
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        chat_ids.add(int(item))
    return frozenset(chat_ids)
