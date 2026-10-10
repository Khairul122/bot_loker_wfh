"""Unit tests for 9Router LLM provider and router."""

from __future__ import annotations

import json
from bot_loker_wfh import database
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
        conn = database.connect()
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

    def test_legacy_provider_is_ignored(self):
        settings = Settings.from_environment({"LLM_PROVIDER": "anthropic"})
        self.assertEqual(settings.llm_provider, "9router")
        router = create_llm_from_settings(settings)
        self.assertIsInstance(router, LLMRouter)

    def test_create_llm_from_settings_9router(self):
        settings = Settings(
            environment="test",
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

    def test_router_set_and_reset_active_model(self):
        prov = MagicMock()
        router = LLMRouter([(prov, "default-model"), (prov, "fallback-model")])
        self.assertEqual(router.active_model, "default-model")

        router.set_active_model("Antigravity")
        self.assertEqual(router.active_model, "Antigravity")
        self.assertEqual(router.chain[0][1], "Antigravity")
        self.assertEqual(router.chain[1][1], "fallback-model")

        router.reset_model()
        self.assertEqual(router.active_model, "default-model")
        self.assertEqual(router.chain[0][1], "default-model")

    def test_fetch_9router_models_categorized(self):
        from bot_loker_wfh.llm import fetch_9router_models_categorized

        mock_data = {
            "data": [
                {"id": "Antigravity", "owned_by": "combo"},
                {"id": "GithubCopilot", "owned_by": "combo"},
                {"id": "ag/gemini-3.8-flash", "owned_by": "ag", "capabilities": {"vision": True}},
                {"id": "gh/gpt-4o", "owned_by": "gh", "capabilities": {"vision": True}},
                {"id": "text-only-model", "owned_by": "other", "capabilities": {"vision": False}},
            ]
        }

        with patch("bot_loker_wfh.llm.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(mock_data).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            result = fetch_9router_models_categorized()
            self.assertIn("Antigravity", result["combo"])
            self.assertIn("GithubCopilot", result["combo"])
            self.assertIn("ag/gemini-3.8-flash", result["vision"])
            self.assertIn("gh/gpt-4o", result["vision"])
            self.assertNotIn("text-only-model", result["vision"])
            self.assertNotIn("text-only-model", result["combo"])


class RouterCallableTest(unittest.TestCase):
    def test_router_is_callable_like_a_provider(self):
        from bot_loker_wfh.llm import LLMResult, LLMRouter

        class Fake:
            name = "fake"

            def complete(self, messages, **kwargs):
                return LLMResult(text="ok:" + messages[0]["content"], provider="fake", model="m")

        self.assertEqual(LLMRouter([(Fake(), "m")])("hi"), "ok:hi")
