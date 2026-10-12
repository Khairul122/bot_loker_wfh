"""Contract and routing tests for the Hermes Agent bridge."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from bot_loker_wfh.config import Settings
from bot_loker_wfh.llm import (
    HermesAgentClient,
    HermesTaskRunner,
    HERMES_REQUIRED_SKILLS,
    LLMError,
    LLMResult,
    LLMRouter,
    create_llm_from_settings,
)


class HermesClientTest(unittest.TestCase):
    def client(self, key="test-token"):
        return HermesAgentClient("http://127.0.0.1:8642/v1", key, "loker-draft")

    def test_chat_request_sends_task_context_and_reads_runtime_metadata(self):
        client = self.client()
        response = MagicMock()
        response.read.return_value = json.dumps({
            "choices": [{"message": {"content": "Draft ready"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            "runtime": {"provider": "custom", "model": "combo-model"},
        }).encode()
        response.__enter__.return_value = response

        with patch("bot_loker_wfh.llm.urlopen", return_value=response) as request_call:
            result = client.complete(
                [{"role": "user", "content": "draft"}],
                model="loker-draft",
                system_prompt="You are Leva.",
                session_key="loker:employee:leva",
                session_id="cover-letter-123",
            )

        request = request_call.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")
        self.assertEqual(payload["model"], "loker-draft")
        self.assertEqual(payload["messages"][0], {"role": "system", "content": "You are Leva."})
        self.assertEqual(request.get_header("X-hermes-session-key"), "loker:employee:leva")
        self.assertEqual(result.provider, "custom")
        self.assertEqual(result.model, "combo-model")
        self.assertEqual(result.text, "Draft ready")
        self.assertEqual((result.prompt_tokens, result.completion_tokens), (12, 4))

    def test_missing_key_fails_closed_without_network(self):
        with patch("bot_loker_wfh.llm.urlopen") as request_call:
            with self.assertRaises(LLMError) as raised:
                self.client("").complete([{"role": "user", "content": "draft"}])
        self.assertEqual(raised.exception.code, "misconfigured")
        request_call.assert_not_called()

    def test_client_rejects_plain_http_to_remote_host(self):
        with self.assertRaises(ValueError):
            HermesAgentClient("http://hermes.internal:8642/v1", "key", "alias")

    def test_client_accepts_https_remote_host(self):
        client = HermesAgentClient("https://hermes.internal/v1", "key", "alias")
        self.assertEqual(client.base_url, "https://hermes.internal/v1")

    def test_client_accepts_profile_scoped_api_server_url(self):
        client = HermesAgentClient(
            "http://127.0.0.1:8642/p/loker-wfh/v1", "key", "alias"
        )
        self.assertEqual(client.base_url, "http://127.0.0.1:8642/p/loker-wfh/v1")
        self.assertEqual(client.server_url, "http://127.0.0.1:8642/p/loker-wfh")

    def test_health_and_readiness_verify_runtime_contract_without_chat(self):
        client = self.client()
        with patch.object(client, "_get_json", return_value={"status": "ok", "version": "0.22"}) as get:
            health = client.check_health()
            self.assertTrue(health["ok"])
            self.assertEqual(get.call_args.args[0], "http://127.0.0.1:8642/health")

        with patch.object(client, "_get_json", return_value={"status": "ok", "version": "0.22"}), \
             patch.object(client, "list_toolset_inventory", return_value=[
                 {"name": "skills", "enabled": True, "tools": ["skills_list", "skill_view"]},
                 {"name": "memory", "enabled": True, "tools": ["memory"]},
                 {"name": "delegation", "enabled": True, "tools": ["delegate_task"]},
             ]), \
             patch.object(client, "list_skill_names", return_value=tuple(HERMES_REQUIRED_SKILLS)), \
             patch.object(client, "list_models", return_value=["loker-draft", "loker-form", "loker-answer"]):
            readiness = client.check_readiness(required_models=("loker-draft", "loker-form", "loker-answer"))
        self.assertTrue(readiness["ok"])
        self.assertEqual(readiness["version"], "0.22")

    def test_readiness_rejects_dangerous_toolsets_and_missing_aliases(self):
        client = self.client()
        with patch.object(client, "_get_json", return_value={"status": "ok"}), \
             patch.object(client, "list_toolset_inventory", return_value=[
                 {"name": "skills", "enabled": True, "tools": ["skills_list", "skill_view", "skill_manage"]},
                 {"name": "memory", "enabled": True, "tools": ["memory"]},
                 {"name": "delegation", "enabled": True, "tools": ["delegate_task"]},
                 {"name": "terminal", "enabled": True, "tools": ["terminal"]},
             ]), \
             patch.object(client, "list_skill_names", return_value=tuple(HERMES_REQUIRED_SKILLS)), \
             patch.object(client, "list_models", return_value=["loker-draft"]):
            readiness = client.check_readiness(required_models=("loker-draft", "loker-form"))
        self.assertFalse(readiness["ok"])
        self.assertEqual(readiness["unexpected_toolsets"], ["terminal"])
        self.assertIn("skill_manage", readiness["advertised_tools"])
        self.assertEqual(readiness["missing_models"], ["loker-form"])

    def test_readiness_requires_every_employee_skill(self):
        client = self.client()
        with patch.object(client, "_get_json", return_value={"status": "ok"}), \
             patch.object(client, "list_toolset_inventory", return_value=[
                 {"name": "skills", "enabled": True, "tools": ["skills_list", "skill_view"]},
                 {"name": "memory", "enabled": True, "tools": ["memory"]},
                 {"name": "delegation", "enabled": True, "tools": ["delegate_task"]},
             ]), \
             patch.object(client, "list_skill_names", return_value=("loker-employee-leva",)), \
             patch.object(client, "list_models", return_value=[]):
            readiness = client.check_readiness()
        self.assertFalse(readiness["ok"])
        self.assertEqual(len(readiness["missing_skills"]), len(HERMES_REQUIRED_SKILLS) - 1)

    def test_readiness_without_key_makes_no_request(self):
        client = self.client("")
        with patch.object(client, "_get_json") as get:
            readiness = client.check_readiness()
        self.assertEqual(readiness["status"], "misconfigured")
        get.assert_not_called()

    def test_toolset_inventory_accepts_documented_array_response(self):
        client = self.client()
        with patch.object(client, "_get_json", return_value=[
            {"name": "skills", "enabled": True, "tools": []},
            {"name": "memory", "enabled": True, "tools": []},
            {"name": "delegation", "enabled": True, "tools": []},
            {"name": "terminal", "enabled": False, "tools": []},
        ]):
            self.assertEqual(client.list_enabled_toolsets(), ("skills", "memory", "delegation"))

    def test_session_headers_reject_control_characters(self):
        with self.assertRaises(ValueError):
            self.client().complete(
                [{"role": "user", "content": "x"}], session_key="bad\nkey"
            )


class HermesRouterTest(unittest.TestCase):
    def test_settings_default_to_hermes_for_unknown_provider_names(self):
        settings = Settings.from_environment({"LLM_PROVIDER": "unknown-provider"})
        self.assertEqual(settings.llm_provider, "hermes")
        self.assertIsNone(settings.hermes_api_key)

    def test_settings_select_template_only_as_offline_alternative(self):
        self.assertEqual(Settings.from_environment({"LLM_PROVIDER": "template"}).llm_provider, "template")
        self.assertEqual(Settings.from_environment({"LLM_PROVIDER": "anthropic"}).llm_provider, "hermes")

    def test_factory_creates_only_hermes_provider_and_task_aliases(self):
        settings = Settings.from_environment({
            "LLM_PROVIDER": "hermes",
            "HERMES_API_KEY": "unit-test",
            "HERMES_MODEL_DRAFT": "draft-route",
            "HERMES_MODEL_FORM": "form-route",
            "HERMES_MODEL_ANSWER": "answer-route",
        })
        router = create_llm_from_settings(settings)
        self.assertEqual(router.provider_name, "hermes")
        self.assertIsInstance(router.chain[0][0], HermesAgentClient)
        self.assertEqual(router.task_models, {
            "draft": "draft-route", "form": "form-route", "answer": "answer-route"
        })

    def test_template_mode_creates_no_agent(self):
        from bot_loker_wfh.llm import create_chat_llm

        settings = Settings.from_environment({"LLM_PROVIDER": "template"})
        self.assertIsNone(create_llm_from_settings(settings))
        self.assertIsNone(create_chat_llm(settings))

    def test_task_runner_builds_employee_persona_and_native_memory_context(self):
        provider = MagicMock()
        provider.name = "hermes"
        provider.complete.return_value = LLMResult("Answer", "hermes", "answer-route")
        router = LLMRouter([(provider, "draft-route")], task_models={"answer": "answer-route"})
        runner = router.for_task(
            "answer", persona="sari", memory_context="Owner says be concise.",
            session_key="loker:employee:sari", session_id="owner-chat-sari",
        )

        self.assertIsInstance(runner, HermesTaskRunner)
        self.assertEqual(runner("question"), "Answer")
        request = provider.complete.call_args.kwargs
        self.assertIn("employee Sari", request["system_prompt"])
        self.assertIn("loker-employee-sari", request["system_prompt"])
        self.assertIn("be concise", request["system_prompt"])
        self.assertEqual(request["session_key"], "loker:employee:sari")

    def test_router_records_success_and_error_metadata(self):
        recorder = MagicMock()
        provider = MagicMock()
        provider.name = "hermes"
        provider.complete.return_value = LLMResult("ok", "custom", "model-a", latency_ms=18, prompt_tokens=9, completion_tokens=3)
        router = LLMRouter([(provider, "loker-draft")], recorder=recorder)
        router.complete("draft", [{"role": "user", "content": "x"}], run_id="run-a")
        success = recorder.record_call.call_args.kwargs
        self.assertEqual((success["provider"], success["model"], success["latency_ms"]), ("custom", "model-a", 18))
        self.assertEqual((success["prompt_tokens"], success["completion_tokens"]), (9, 3))

        recorder.reset_mock()
        provider.complete.side_effect = LLMError("network_error")
        with self.assertRaises(LLMError):
            router.complete("draft", [{"role": "user", "content": "x"}])
        self.assertEqual(recorder.record_call.call_args.kwargs["status"], "error")
        self.assertEqual(recorder.record_call.call_args.kwargs["error_code"], "network_error")

    def test_template_fallback_does_not_use_network(self):
        provider = MagicMock()
        provider.name = "hermes"
        provider.complete.side_effect = LLMError("network_error")
        router = LLMRouter([(provider, "loker-draft")])
        with self.assertRaises(LLMError):
            router("draft")


class CheckLLMCommandTest(unittest.TestCase):
    def test_check_llm_checks_readiness_without_model_completion(self):
        from bot_loker_wfh import __main__ as app

        client = MagicMock()
        client.check_readiness.return_value = {
            "ok": True, "status": "ok", "version": "0.22",
            "toolsets": ["delegation", "memory", "skills"],
            "models": ["loker-draft", "loker-form", "loker-answer"],
        }
        with patch("bot_loker_wfh.llm.HermesAgentClient", return_value=client), patch("builtins.print") as output:
            self.assertEqual(app.main(["check-llm"]), 0)
        client.check_readiness.assert_called_once()
        self.assertIn("Hermes Agent siap", output.call_args.args[0])

    def test_check_llm_explains_missing_hermes_key(self):
        from bot_loker_wfh import __main__ as app

        client = MagicMock()
        client.check_readiness.return_value = {
            "ok": False, "status": "misconfigured", "toolsets": [], "models": [],
        }
        with patch("bot_loker_wfh.llm.HermesAgentClient", return_value=client), patch("builtins.print") as output:
            self.assertEqual(app.main(["check-llm"]), 1)
        self.assertIn("HERMES_API_KEY belum dikonfigurasi", output.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
