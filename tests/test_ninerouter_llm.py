"""Unit tests for 9Router LLM provider and router."""

from __future__ import annotations

import json
import sqlite3
import unittest
from unittest.mock import MagicMock, patch

from bot_loker_wfh.config import Settings
from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.llm import (
    LLMError,
    LLMResult,
    LLMRouter,
    OpenAICompatibleProvider,
    create_llm_from_settings,
)
from bot_loker_wfh.llm_calls import LLMCallRecorder


class TestNineRouterLLM(unittest.TestCase):
    def test_openai_compatible_provider_success(self):
        prov = OpenAICompatibleProvider("http://localhost:20128/v1", "key", "test-model")
        mock_response = {
            "choices": [{"message": {"content": "Halo dunia"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

        with patch.object(prov, "_make_request", return_value=mock_response):
            res = prov.complete([{"role": "user", "content": "hi"}])
            self.assertEqual(res.text, "Halo dunia")
            self.assertEqual(res.model, "test-model")
            self.assertEqual(res.prompt_tokens, 10)
            self.assertEqual(res.completion_tokens, 5)

    def test_router_fallback_on_failure(self):
        prov1 = MagicMock()
        prov1.complete.side_effect = LLMError("rate_limited")
        prov1.name = "prov1"

        prov2 = MagicMock()
        prov2.name = "prov2"
        prov2.complete.return_value = LLMResult("Success from fallback", "prov2", "fallback-model")

        chain = [(prov1, "model-1"), (prov2, "fallback-model")]
        router = LLMRouter(chain, task_budget_seconds=10.0)

        res = router.complete("draft", [{"role": "user", "content": "test"}])
        self.assertEqual(res.text, "Success from fallback")
        self.assertEqual(res.model, "fallback-model")

    def test_router_records_call(self):
        conn = sqlite3.connect(":memory:")
        apply_schema(conn)

        recorder = MagicMock()
        prov = MagicMock()
        prov.name = "test_prov"
        prov.complete.return_value = LLMResult("Test output", "test_prov", "model_x")

        router = LLMRouter([(prov, "model_x")], recorder=recorder)
        router.complete("draft", [{"role": "user", "content": "prompt"}], run_id="r-123")

        recorder.record_call.assert_called_once()
        args = recorder.record_call.call_args[1]
        self.assertEqual(args["task"], "draft")
        self.assertEqual(args["status"], "success")
        self.assertEqual(args["run_id"], "r-123")

    def test_create_llm_from_settings_9router(self):
        settings = Settings(
            environment="test",
            database_url="sqlite:///data/test.db",
            external_jobs_enabled=False,
            telegram_bot_token=None,
            telegram_allowed_chat_ids=frozenset(),
            llm_provider="9router",
            ninerouter_model="loker-draft",
            ninerouter_fallback_models=("glm-5.1",),
        )
        router = create_llm_from_settings(settings)
        self.assertIsInstance(router, LLMRouter)
        self.assertEqual(len(router.chain), 2)
