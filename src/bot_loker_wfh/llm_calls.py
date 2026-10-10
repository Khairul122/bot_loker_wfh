"""Recorder for LLM API calls."""

from __future__ import annotations

import uuid
from typing import Any

from . import database


class LLMCallRecorder:
    def record_call(
        self,
        *,
        task: str,
        provider: str,
        model: str,
        status: str,
        attempt: int = 1,
        run_id: str | None = None,
        error_code: str | None = None,
        latency_ms: int | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        application_id: str | None = None,
    ) -> None:
        call_id = str(uuid.uuid4())
        try:
            with database.session() as conn:
                conn.execute(
                    """
                    INSERT INTO llm_calls (
                        id, run_id, task, provider, model, attempt,
                        status, error_code, latency_ms, prompt_tokens,
                        completion_tokens, application_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        call_id,
                        run_id,
                        task,
                        provider,
                        model,
                        attempt,
                        status,
                        error_code,
                        latency_ms,
                        prompt_tokens,
                        completion_tokens,
                        application_id,
                    ),
                )
                conn.commit()
        except Exception:
            pass  # Suppress recorder DB errors to keep core flow intact
