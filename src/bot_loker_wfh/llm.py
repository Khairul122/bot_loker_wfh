"""Hermes Agent task runner and call recording."""

from __future__ import annotations

import json
import ipaddress
import re
import time
from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from bot_loker_wfh.llm_calls import LLMCallRecorder

HERMES_REQUIRED_TOOLSETS = frozenset({"skills", "memory", "delegation"})


@dataclass(frozen=True)
class LLMResult:
    text: str
    provider: str
    model: str
    latency_ms: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LLMError(RuntimeError):
    def __init__(self, code: str, message: str = "", *, retryable: bool = False):
        super().__init__(message or code)
        self.code = code
        self.retryable = retryable
        self.latency_ms: int | None = None


class HermesAgentClient:
    """Authenticated bridge to Hermes Agent's API Server runtime."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        model: str = "hermes-agent",
        *,
        max_tokens: int = 800,
        temperature: float = 0.4,
        timeout: float = 60.0,
    ) -> None:
        normalized_url = base_url.strip().rstrip("/")
        _validate_hermes_base_url(normalized_url)
        self.base_url = normalized_url
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.name = "hermes"
        self.api_key = (api_key or "").strip()
        self.server_url = normalized_url[:-3]

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        json_mode: bool = False,
        model: str | None = None,
        system_prompt: str = "",
        session_key: str | None = None,
        session_id: str | None = None,
    ) -> LLMResult:
        if not self.api_key:
            raise LLMError("misconfigured", "HERMES_API_KEY is required")
        target_model = model or self.model
        request_messages = list(messages)
        if system_prompt:
            request_messages.insert(0, {"role": "system", "content": system_prompt})
        payload: dict[str, Any] = {
            "model": target_model,
            "messages": request_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        if session_key:
            headers["X-Hermes-Session-Key"] = _validate_session_header(session_key)
        if session_id:
            headers["X-Hermes-Session-Id"] = _validate_session_header(session_id)
        started = time.monotonic()
        try:
            result = self._make_request(
                f"{self.base_url}/chat/completions", payload, headers
            )
        except LLMError as error:
            error.latency_ms = int((time.monotonic() - started) * 1000)
            raise
        try:
            choice_rows = result.get("choices", [])
            if not isinstance(choice_rows, list) or not choice_rows:
                raise LLMError("bad_response", "Hermes returned no assistant response")
            message = choice_rows[0].get("message", {})
            content = message.get("content", "") if isinstance(message, dict) else ""
            if not isinstance(content, str):
                raise LLMError("bad_response", "Hermes returned an invalid assistant response")
        except (AttributeError, IndexError, TypeError) as error:
            raise LLMError("bad_response", "Hermes returned an invalid assistant response") from error
        except LLMError as error:
            error.latency_ms = int((time.monotonic() - started) * 1000)
            raise
        usage = result.get("usage", {}) if isinstance(result.get("usage"), dict) else {}
        runtime = result.get("runtime", {}) if isinstance(result.get("runtime"), dict) else {}
        served_model = runtime.get("model") or target_model
        served_provider = runtime.get("provider") or "hermes"
        return LLMResult(
            text=content.strip(),
            provider=str(served_provider),
            model=str(served_model),
            latency_ms=int((time.monotonic() - started) * 1000),
            prompt_tokens=usage.get("prompt_tokens", usage.get("input_tokens")),
            completion_tokens=usage.get("completion_tokens", usage.get("output_tokens")),
        )

    def _make_request(
        self, url: str, payload: dict[str, Any], headers: dict[str, str]
    ) -> dict[str, Any]:
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return _parse_chat_body(response.read().decode("utf-8", "replace"))
        except HTTPError as error:
            raise LLMError(
                _map_http_status_to_code(error.code),
                f"Hermes API returned HTTP {error.code}",
                retryable=error.code in {429, 502, 503, 504},
            ) from None
        except (URLError, TimeoutError, OSError) as error:
            timed_out = isinstance(error, TimeoutError) or isinstance(
                getattr(error, "reason", None), TimeoutError
            )
            raise LLMError(
                "timeout" if timed_out else "network_error",
                "Hermes API request timed out" if timed_out else "Hermes API is unreachable",
                retryable=timed_out,
            ) from None

    def list_models(self) -> list[str]:
        if not self.api_key:
            raise LLMError("misconfigured", "HERMES_API_KEY is required")
        payload = self._get_json(f"{self.base_url}/models")
        rows = payload if isinstance(payload, list) else payload.get("data", [])
        return [item["id"] for item in rows if isinstance(item, dict) and isinstance(item.get("id"), str)] if isinstance(rows, list) else []

    def __call__(self, prompt: str) -> str:
        return self.complete([{"role": "user", "content": prompt}]).text

    def check_health(self) -> dict[str, Any]:
        if not self.api_key:
            return {"ok": False, "status": "misconfigured", "version": ""}
        try:
            payload = self._get_json(f"{self.server_url}/health")
        except LLMError as err:
            return {"ok": False, "status": err.code, "version": ""}
        status = payload.get("status", "unknown")
        return {
            "ok": status == "ok",
            "status": status if isinstance(status, str) else "unknown",
            "version": payload.get("version", "") if isinstance(payload.get("version", ""), str) else "",
        }

    def list_enabled_toolsets(self) -> tuple[str, ...]:
        if not self.api_key:
            raise LLMError("misconfigured", "HERMES_API_KEY is required")
        payload = self._get_json(f"{self.base_url}/toolsets")
        rows = payload if isinstance(payload, list) else payload.get("data", [])
        if not isinstance(rows, list):
            raise LLMError("bad_response", "invalid Hermes toolset response")
        return tuple(
            item["name"]
            for item in rows
            if isinstance(item, dict)
            and item.get("enabled") is True
            and isinstance(item.get("name"), str)
        )

    def check_readiness(
        self, *, required_models: tuple[str, ...] = ()
    ) -> dict[str, Any]:
        if not self.api_key:
            return {"ok": False, "status": "misconfigured", "toolsets": [], "models": []}
        try:
            payload = self._get_json(f"{self.server_url}/health/detailed")
            toolsets = self.list_enabled_toolsets()
            models = tuple(self.list_models())
        except LLMError as error:
            return {"ok": False, "status": error.code, "toolsets": [], "models": []}
        status = payload.get("status", "unknown")
        missing_toolsets = HERMES_REQUIRED_TOOLSETS - set(toolsets)
        unexpected_toolsets = set(toolsets) - HERMES_REQUIRED_TOOLSETS
        missing_models = set(required_models) - set(models)
        return {
            "ok": status == "ok" and not missing_toolsets and not unexpected_toolsets and not missing_models,
            "status": status if isinstance(status, str) else "unknown",
            "toolsets": list(toolsets),
            "models": list(models),
            "missing_toolsets": sorted(missing_toolsets),
            "unexpected_toolsets": sorted(unexpected_toolsets),
            "missing_models": sorted(missing_models),
            "version": payload.get("version", "") if isinstance(payload.get("version", ""), str) else "",
        }

    def _get_json(self, url: str) -> dict[str, Any] | list[Any]:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8", "replace"))
        except HTTPError as err:
            raise LLMError(
                _map_http_status_to_code(err.code),
                f"Hermes API returned HTTP {err.code}",
                retryable=err.code in {429, 502, 503, 504},
            ) from None
        except (URLError, TimeoutError, OSError) as err:
            is_timeout = isinstance(err, TimeoutError) or isinstance(getattr(err, "reason", None), TimeoutError)
            raise LLMError(
                "timeout" if is_timeout else "network_error",
                "Hermes API request timed out" if is_timeout else "Hermes API is unreachable",
                retryable=is_timeout,
            ) from None
        except (UnicodeError, ValueError):
            raise LLMError("bad_response", "invalid Hermes API response") from None
        if not isinstance(payload, (dict, list)):
            raise LLMError("bad_response", "invalid Hermes API response")
        return payload


def _validate_hermes_base_url(base_url: str) -> None:
    try:
        parsed = urlsplit(base_url)
        hostname = parsed.hostname or ""
        path = parsed.path.rstrip("/")
        if hostname.lower() == "localhost":
            is_loopback = True
        else:
            try:
                is_loopback = ipaddress.ip_address(hostname).is_loopback
            except ValueError:
                is_loopback = False
    except ValueError:
        raise ValueError("HERMES_BASE_URL must be a valid URL") from None
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or path != "/v1"
        or (parsed.scheme == "http" and not is_loopback)
    ):
        raise ValueError("HERMES_BASE_URL must use HTTPS remotely or loopback HTTP and end in /v1")


def _parse_chat_body(body: str) -> dict[str, Any]:
    """Parse a regular JSON response or Hermes server-sent events."""
    body = body.strip()
    try:
        return json.loads(body)
    except ValueError:
        pass
    json_prefix, marker, suffix = body.partition("data:")
    if marker and suffix.strip() == "[DONE]":
        try:
            payload = json.loads(json_prefix.strip())
            if isinstance(payload, dict):
                return payload
        except ValueError:
            pass
    text, last = [], {}
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("data:") or line == "data: [DONE]":
            continue
        try:
            chunk = json.loads(line[5:])
        except ValueError:
            continue
        last = chunk
        for choice in chunk.get("choices") or []:
            part = (choice.get("delta") or choice.get("message") or {}).get("content")
            if part:
                text.append(part)
    if not last:
        raise LLMError("bad_response", "unreadable response body")
    return {**last, "choices": [{"message": {"content": "".join(text)}}]}


def _validate_session_header(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256 or any(ord(char) < 32 for char in value):
        raise ValueError("Hermes session identifiers must be 1-256 printable characters")
    return value


def _map_http_status_to_code(status: int) -> str:
    if status == 401:
        return "unauthorized"
    if status == 403:
        return "forbidden"
    if status == 404:
        return "model_not_found"
    if status == 429:
        return "rate_limited"
    if status == 400:
        return "bad_request"
    if 500 <= status <= 599:
        return "upstream_error"
    return "unexpected_error"


class LLMRouter:
    def __init__(
        self,
        chain: list[tuple[HermesAgentClient, str]],
        recorder: LLMCallRecorder | None = None,
        task_budget_seconds: float = 90.0,
        task_models: Mapping[str, str] | None = None,
    ):
        self.chain = chain
        self.original_chain = list(chain)
        self.recorder = recorder
        self.task_budget_seconds = task_budget_seconds
        self.task_models = dict(task_models or {})
        self._last_result: LLMResult | None = None
        self._active_model_override: str | None = None

    @property
    def active_model(self) -> str:
        if self._active_model_override:
            return self._active_model_override
        if self.chain:
            return self.chain[0][1]
        return "none"

    def set_active_model(self, model: str) -> None:
        self._active_model_override = model
        if self.chain:
            first_provider = self.chain[0][0]
            self.chain = [(first_provider, model)] + list(self.original_chain[1:])

    def reset_model(self) -> None:
        self._active_model_override = None
        self.chain = list(self.original_chain)

    @property
    def last_result(self) -> LLMResult | None:
        return self._last_result

    def complete(
        self,
        task: str,
        messages: list[dict[str, Any]],
        *,
        json_mode: bool = False,
        run_id: str | None = None,
        application_id: str | None = None,
        persona: str | None = None,
        memory_context: str = "",
        session_key: str | None = None,
        session_id: str | None = None,
        system_prompt: str = "",
    ) -> LLMResult:
        start_task_time = time.monotonic()
        for provider, model in self.chain:
            if time.monotonic() - start_task_time > self.task_budget_seconds:
                break
            requested_model = model
            if not self._active_model_override:
                requested_model = self.task_models.get(task, model)
            provider_name = provider.name
            for attempt in (1, 2):
                if time.monotonic() - start_task_time > self.task_budget_seconds:
                    break
                attempt_started = time.monotonic()
                try:
                    res = provider.complete(
                        messages,
                        json_mode=json_mode,
                        model=requested_model,
                        system_prompt=_task_system_prompt(
                            task, persona, memory_context, system_prompt
                        ),
                        session_key=session_key,
                        session_id=session_id,
                    )
                    if not res.text.strip():
                        empty_error = LLMError("empty_response", retryable=True)
                        empty_error.latency_ms = res.latency_ms
                        raise empty_error
                    if json_mode:
                        try:
                            json.loads(res.text)
                        except Exception as jerr:
                            invalid_error = LLMError(
                                "invalid_json", "Invalid JSON output", retryable=True
                            )
                            invalid_error.latency_ms = res.latency_ms
                            raise invalid_error from jerr

                    self._last_result = res
                    if self.recorder:
                        self.recorder.record_call(
                            task=task,
                            provider=res.provider,
                            model=res.model,
                            status="success",
                            attempt=attempt,
                            run_id=run_id,
                            latency_ms=res.latency_ms,
                            prompt_tokens=res.prompt_tokens,
                            completion_tokens=res.completion_tokens,
                            application_id=application_id,
                        )
                    return res
                except LLMError as err:
                    if err.latency_ms is None:
                        err.latency_ms = int((time.monotonic() - attempt_started) * 1000)
                    if self.recorder:
                        self.recorder.record_call(
                            task=task,
                            provider=provider_name,
                            model=requested_model,
                            status="error",
                            attempt=attempt,
                            run_id=run_id,
                            error_code=err.code,
                            latency_ms=err.latency_ms,
                            application_id=application_id,
                        )
                    if err.code == "rate_limited" and attempt == 1:
                        time.sleep(1.0)
                        continue
                    break
                except Exception:
                    if self.recorder:
                        self.recorder.record_call(
                            task=task,
                            provider=provider_name,
                            model=requested_model,
                            status="error",
                            attempt=attempt,
                            run_id=run_id,
                            error_code="unexpected_error",
                            latency_ms=int((time.monotonic() - attempt_started) * 1000),
                            application_id=application_id,
                        )
                    break

        raise LLMError("all_providers_failed", "All configured AI models failed")

    def __call__(self, prompt: str) -> str:
        """Plain prompt -> text, so callers can treat the router like a single provider."""
        return self.for_task(
            "draft", persona="leva", session_key="loker:employee:leva"
        )(prompt)

    def for_task(
        self,
        task: str,
        *,
        run_id: str | None = None,
        application_id: str | None = None,
        persona: str | None = None,
        system_prompt: str = "",
        memory_context: str = "",
        session_key: str | None = None,
        session_id: str | None = None,
    ) -> "HermesTaskRunner":
        return HermesTaskRunner(
            self, task, run_id=run_id, application_id=application_id,
            persona=persona, system_prompt=system_prompt,
            memory_context=memory_context, session_key=session_key,
            session_id=session_id,
        )


class HermesTaskRunner:
    def __init__(
        self,
        router: LLMRouter,
        task: str,
        *,
        run_id: str | None = None,
        application_id: str | None = None,
        persona: str | None = None,
        system_prompt: str = "",
        memory_context: str = "",
        session_key: str | None = None,
        session_id: str | None = None,
    ) -> None:
        self.router = router
        self.task = task
        self.run_id = run_id
        self.application_id = application_id
        self.persona = persona
        self.system_prompt = system_prompt
        self.memory_context = memory_context
        self.session_key = session_key
        self.session_id = session_id

    def __call__(self, prompt: str) -> str:
        result = self.router.complete(
            self.task,
            [{"role": "user", "content": prompt}],
            run_id=self.run_id,
            application_id=self.application_id,
            persona=self.persona,
            system_prompt=self.system_prompt,
            memory_context=self.memory_context,
            session_key=self.session_key,
            session_id=self.session_id,
        )
        return result.text

    @property
    def last_result(self) -> LLMResult | None:
        return self.router.last_result

    def with_context(self, **context: Any) -> "HermesTaskRunner":
        values = {
            "run_id": self.run_id,
            "application_id": self.application_id,
            "persona": self.persona,
            "system_prompt": self.system_prompt,
            "memory_context": self.memory_context,
            "session_key": self.session_key,
            "session_id": self.session_id,
        }
        values.update({key: value for key, value in context.items() if key in values})
        return self.router.for_task(self.task, **values)


def create_chat_llm(settings: Any, record_calls: bool = False) -> Callable[[str], str] | None:
    """Fast chat answers (office Q&A): use the configured provider without a slow agent run.

    Template mode keeps its deterministic offline fallback.
    """
    if getattr(settings, "llm_provider", "hermes") == "template":
        return None
    router = create_llm_from_settings(settings, record_calls)
    return router.for_task("answer") if isinstance(router, LLMRouter) else router


def create_llm_from_settings(settings: Any, record_calls: bool = False) -> LLMRouter | None:
    provider_name = getattr(settings, "llm_provider", "hermes")
    if provider_name == "template":
        return None
    recorder = LLMCallRecorder() if record_calls else None
    draft_model = getattr(settings, "hermes_model_draft", "loker-draft") or "loker-draft"
    task_models = {
        "draft": draft_model,
        "form": getattr(settings, "hermes_model_form", "loker-form") or "loker-form",
        "answer": getattr(settings, "hermes_model_answer", "loker-answer") or "loker-answer",
    }
    provider = HermesAgentClient(
        getattr(settings, "hermes_base_url", "http://127.0.0.1:8642/v1"),
        getattr(settings, "hermes_api_key", None),
        draft_model,
        timeout=getattr(settings, "llm_timeout_seconds", 60.0),
    )
    router = LLMRouter(
        [(provider, draft_model)],
        recorder=recorder,
        task_budget_seconds=getattr(settings, "llm_task_budget_seconds", 90.0),
        task_models=task_models,
    )
    setattr(router, "provider_name", "hermes")
    return router


def _task_system_prompt(
    task: str, persona: str | None, memory_context: str, extra: str
) -> str:
    sections = [
        "You are running inside Hermes Agent for the Loker WFH application. "
        "Use available Hermes skills and agent tools only when useful. Never submit applications, "
        "send bids, bypass CAPTCHA, or change application records; the host application owns those actions."
    ]
    if persona:
        from .office_desk import ROLES

        if persona not in ROLES:
            raise ValueError("unknown employee persona")
        sections.append(
            f"Act as employee {persona.title()}, whose role is {ROLES[persona]}. "
            f"Load the Hermes skill loker-employee-{persona} with skill_view before doing this task."
        )
    sections.append(f"Task type: {task}.")
    if memory_context:
        sections.append("Authoritative employee memories/instructions from application storage:\n" + memory_context[:6000])
    if extra:
        sections.append(extra[:6000])
    return "\n\n".join(sections)
