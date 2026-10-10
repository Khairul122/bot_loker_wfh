"""9Router LLM provider and routing."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bot_loker_wfh.llm_calls import LLMCallRecorder


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


class OpenAICompatibleProvider:
    """OpenAI-compatible API provider (9Router, local proxies)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        max_tokens: int = 800,
        temperature: float = 0.4,
        timeout: float = 60.0,
        name: str = "9router",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or "sk-dummy"
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.name = name

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        json_mode: bool = False,
        model: str | None = None,
    ) -> LLMResult:
        target_model = model or self.model
        url = f"{self.base_url}/chat/completions"
        start_time = time.monotonic()

        payload_dict: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if json_mode:
            payload_dict["response_format"] = {"type": "json_object"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        try:
            res_payload = self._make_request(url, payload_dict, headers)
        except LLMError as err:
            if json_mode and err.code == "bad_request":
                # Fallback once without response_format if unsupported by provider
                payload_dict.pop("response_format", None)
                try:
                    res_payload = self._make_request(url, payload_dict, headers)
                except LLMError:
                    raise err
            else:
                raise err

        latency_ms = int((time.monotonic() - start_time) * 1000)
        choices = res_payload.get("choices", [])
        text = ""
        if choices and isinstance(choices, list):
            message = choices[0].get("message", {})
            text = message.get("content") or ""
        text = text.strip()

        usage = res_payload.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")

        return LLMResult(
            text=text,
            provider=self.name,
            model=target_model,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    def _make_request(
        self, url: str, payload_dict: dict[str, Any], headers: dict[str, str]
    ) -> dict[str, Any]:
        body = json.dumps(payload_dict).encode("utf-8")
        req = Request(url, data=body, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                return _parse_chat_body(resp.read().decode("utf-8", "replace"))
        except HTTPError as err:
            code = _map_http_status_to_code(err.code)
            raise LLMError(code, f"HTTP {err.code}", retryable=(err.code == 429)) from err
        except (URLError, TimeoutError, OSError) as err:
            code = "timeout" if isinstance(err, TimeoutError) else "network_error"
            raise LLMError(code, str(err), retryable=False) from err

    def list_models(self) -> list[str]:
        url = f"{self.base_url}/models"
        req = Request(url, headers={"Authorization": f"Bearer {self.api_key}"})
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                data = json.load(resp)
                models_data = data.get("data", [])
                return [m.get("id", "") for m in models_data if isinstance(m, dict)]
        except Exception:
            return []

    def __call__(self, prompt: str) -> str:
        res = self.complete([{"role": "user", "content": prompt}])
        return res.text


def _parse_chat_body(body: str) -> dict[str, Any]:
    """Plain JSON, JSON followed by a stray `data: [DONE]` (9Router does this), or an SSE stream."""
    body = body.strip()
    try:
        return json.loads(body)
    except ValueError:
        pass
    try:  # one JSON document with trailing junk
        return json.JSONDecoder().raw_decode(body)[0]
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


def fetch_9router_models_categorized(
    base_url: str = "http://localhost:20128/v1",
    api_key: str = "sk-dummy",
    timeout: float = 5.0,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
            models_data = data.get("data", [])

            combo_models: list[str] = []
            vision_models: list[str] = []

            for m in models_data:
                if not isinstance(m, dict):
                    continue
                mid = m.get("id", "")
                if not mid:
                    continue
                owned = str(m.get("owned_by", "")).lower()
                caps = m.get("capabilities")

                if owned == "combo" or "combo" in mid.lower():
                    combo_models.append(mid)

                if isinstance(caps, dict) and caps.get("vision"):
                    vision_models.append(mid)

            return {
                "combo": sorted(list(set(combo_models))),
                "vision": sorted(list(set(vision_models))),
                "error": None,
            }
    except Exception as err:
        return {"combo": [], "vision": [], "error": str(err)}


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
        chain: list[tuple[Any, str]],
        recorder: LLMCallRecorder | None = None,
        task_budget_seconds: float = 90.0,
    ):
        self.chain = chain
        self.original_chain = list(chain)
        self.recorder = recorder
        self.task_budget_seconds = task_budget_seconds
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
    ) -> LLMResult:
        start_task_time = time.monotonic()
        misconfigured_providers: set[str] = set()

        for provider, model in self.chain:
            if time.monotonic() - start_task_time > self.task_budget_seconds:
                break
            prov_name = getattr(provider, "name", "unknown")
            if prov_name in misconfigured_providers:
                continue

            for attempt in (1, 2):
                if time.monotonic() - start_task_time > self.task_budget_seconds:
                    break
                try:
                    res = provider.complete(messages, json_mode=json_mode, model=model)
                    if not res.text.strip():
                        raise LLMError("empty_response", retryable=True)
                    if json_mode:
                        try:
                            json.loads(res.text)
                        except Exception as jerr:
                            raise LLMError(
                                "invalid_json", "Invalid JSON output", retryable=True
                            ) from jerr

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
                    if self.recorder:
                        self.recorder.record_call(
                            task=task,
                            provider=prov_name,
                            model=model,
                            status="error",
                            attempt=attempt,
                            run_id=run_id,
                            error_code=err.code,
                            application_id=application_id,
                        )
                    if err.code in {"unauthorized", "forbidden"}:
                        misconfigured_providers.add(prov_name)
                        break
                    if err.code == "rate_limited" and attempt == 1:
                        time.sleep(1.0)
                        continue
                    break

        raise LLMError("all_providers_failed", "All configured AI models failed")

    def __call__(self, prompt: str) -> str:
        """Plain prompt -> text, so callers can treat the router like a single provider."""
        return self.for_task("draft")(prompt)

    def for_task(
        self,
        task: str,
        *,
        run_id: str | None = None,
        application_id: str | None = None,
    ) -> Callable[[str], str]:
        def callable_prompt(prompt: str) -> str:
            res = self.complete(
                task=task,
                messages=[{"role": "user", "content": prompt}],
                json_mode=False,
                run_id=run_id,
                application_id=application_id,
            )
            return res.text

        return callable_prompt


def create_chat_llm(settings: Any, record_calls: bool = False) -> Callable[[str], str] | None:
    """Fast chat answers (office Q&A): straight to 9Router, skipping any slow agent run.

    Falls back to the normal chain when 9Router is not configured.
    """
    model = getattr(settings, "ninerouter_model", "")
    if not model:
        router = create_llm_from_settings(settings, record_calls)
        return router.for_task("answer") if isinstance(router, LLMRouter) else router
    provider = OpenAICompatibleProvider(
        getattr(settings, "ninerouter_base_url", "http://localhost:20128/v1"),
        getattr(settings, "ninerouter_api_key", None) or "sk-dummy",
        model,
        timeout=getattr(settings, "llm_timeout_seconds", 60.0),
    )
    chain = [(provider, model)] + [(provider, fb) for fb in getattr(settings, "ninerouter_fallback_models", ()) if fb]
    router = LLMRouter(chain, recorder=LLMCallRecorder() if record_calls else None,
                       task_budget_seconds=getattr(settings, "llm_task_budget_seconds", 90.0))
    return router.for_task("answer")


def create_llm_from_settings(settings: Any, record_calls: bool = False) -> LLMRouter | None:
    recorder = LLMCallRecorder() if record_calls else None
    # Legacy provider environment values are ignored; 9Router is sole selectable provider.
    base_url = getattr(settings, "ninerouter_base_url", "http://localhost:20128/v1")
    api_key = getattr(settings, "ninerouter_api_key", None) or "sk-dummy"
    primary_model = getattr(settings, "ninerouter_model", "") or getattr(settings, "llm_model_draft", "") or "LokerHouse"
    fallbacks = getattr(settings, "ninerouter_fallback_models", ())

    primary_prov = OpenAICompatibleProvider(base_url, api_key, primary_model, timeout=getattr(settings, "llm_timeout_seconds", 60.0))
    chain: list[tuple[Any, str]] = [(primary_prov, primary_model)]

    for fb in fallbacks:
        if fb:
            chain.append((primary_prov, fb))

    router = LLMRouter(chain, recorder=recorder, task_budget_seconds=getattr(settings, "llm_task_budget_seconds", 90.0))
    setattr(router, "provider_name", "9router")
    return router
