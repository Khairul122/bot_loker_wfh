from bot_loker_wfh import database
import unittest
from unittest.mock import MagicMock, patch

from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.telegram_auth import TelegramAuth, TelegramRequest
from bot_loker_wfh.telegram_commands import TelegramCommandHandler


class TelegramCommandHandlerTest(unittest.TestCase):
    def setUp(self):
        self.connection = database.connect()
        apply_schema(self.connection)
        jobs = [
            ("job-candidate", "CANDIDATE", "Backend Developer"),
            ("job-discovered", "DISCOVERED", "Python Developer"),
            ("job-filtered", "FILTERED_OUT", "Old Role"),
        ]
        for job_id, status, title in jobs:
            self.connection.execute(
                "INSERT INTO jobs (id, source, external_id, source_external_key, "
                "canonical_fingerprint, title, company, description, apply_url, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (job_id, "remoteok", job_id, f"remoteok:{job_id}", f"fp:{job_id}", title, "Acme", "desc", "https://example.com/job", status),
            )
        self.connection.execute(
            "INSERT INTO applications (id, job_id, idempotency_key, status, cover_letter, cv_summary) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("app-pending", "job-candidate", "key-pending", "PENDING_APPROVAL", "Cover", "CV"),
        )
        self.connection.execute(
            "INSERT INTO applications (id, job_id, idempotency_key, status, cover_letter, cv_summary) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("app-submitted", "job-discovered", "key-submitted", "SUBMITTED", "Cover", "CV"),
        )
        self.connection.execute(
            "INSERT INTO application_status_history (id, application_id, from_status, to_status, changed_by) "
            "VALUES (?, ?, ?, ?, ?)",
            ("history-1", "app-submitted", "APPROVED", "SUBMITTED", "system"),
        )
        self.connection.commit()
        self.handler = TelegramCommandHandler(
            self.connection,
            auth=TelegramAuth(allowed_chat_ids=frozenset({123})),
        )

    def tearDown(self):
        self.connection.close()

    def test_lowongan_lists_candidate_and_pending_items(self):
        result = self.handler.handle(TelegramRequest(chat_id=123, text="/lowongan"))

        self.assertTrue(result.success)
        self.assertIn("Backend Developer", result.message)
        self.assertIn("PENDING_APPROVAL", result.message)
        self.assertNotIn("Old Role", result.message)

    def test_status_transitions_application_and_records_history(self):
        result = self.handler.handle(
            TelegramRequest(chat_id=123, text="/status app-pending APPROVED")
        )

        self.assertTrue(result.success)
        self.assertIn("APPROVED", result.message)
        self.assertEqual(
            self.connection.execute(
                "SELECT status FROM applications WHERE id = 'app-pending'"
            ).fetchone()[0],
            "APPROVED",
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM application_status_history WHERE application_id = 'app-pending'"
            ).fetchone()[0],
            1,
        )

    def test_invalid_status_transition_is_rejected_safely(self):
        result = self.handler.handle(
            TelegramRequest(chat_id=123, text="/status app-pending SUBMITTED")
        )

        self.assertFalse(result.success)
        self.assertEqual(result.message, "Invalid status transition.")

    def test_laporan_returns_core_counts(self):
        result = self.handler.handle(TelegramRequest(chat_id=123, text="/laporan"))

        self.assertTrue(result.success)
        self.assertIn("Ditemukan 3", result.message)
        self.assertIn("Lolos 1", result.message)
        self.assertIn("Dilamar 1", result.message)
        self.assertIn("Respons 0", result.message)

    def test_unknown_or_malformed_command_is_rejected(self):
        result = self.handler.handle(TelegramRequest(chat_id=123, text="/status"))

        self.assertFalse(result.success)
        self.assertEqual(result.message, "Usage: /status [application_id] [status]")

    def test_unauthorized_command_is_rejected(self):
        result = self.handler.handle(TelegramRequest(chat_id=999, text="/laporan"))

        self.assertFalse(result.success)
        self.assertEqual(result.message, "Unauthorized chat.")

    def test_model_command_lists_combo_and_vision_models(self):
        mock_router = MagicMock()
        mock_router.active_model = "loker-draft"

        mock_info = {
            "combo": ["Antigravity", "GithubCopilot"],
            "vision": ["ag/gemini-3.8-flash", "gh/gpt-4o"],
            "error": None,
        }

        with patch("bot_loker_wfh.telegram_commands.fetch_9router_models_categorized", return_value=mock_info):
            res = self.handler.handle(TelegramRequest(chat_id=123, text="/model"), router=mock_router)
            self.assertTrue(res.success)
            self.assertIn("Combo Models (2)", res.message)
            self.assertIn("Antigravity", res.message)
            self.assertIn("GithubCopilot", res.message)
            self.assertIn("Vision Adapters (2) & Models (2)", res.message)
            self.assertIn("ag/gemini-3.8-flash", res.message)

    def test_model_command_changes_and_resets_model(self):
        mock_router = MagicMock()

        res = self.handler.handle(TelegramRequest(chat_id=123, text="/model Antigravity"), router=mock_router)
        self.assertTrue(res.success)
        self.assertIn("Antigravity", res.message)
        mock_router.set_active_model.assert_called_with("Antigravity")

        res_reset = self.handler.handle(TelegramRequest(chat_id=123, text="/model reset"), router=mock_router)
        self.assertTrue(res_reset.success)
        self.assertIn("dikembalikan ke konfigurasi awal", res_reset.message)
        mock_router.reset_model.assert_called_once()

    def test_filter_command_views_and_updates_filters(self):
        # 1. View filters
        res = self.handler.handle(TelegramRequest(chat_id=123, text="/filter"))
        self.assertTrue(res.success)
        self.assertIn("Filter Scraping Lowongan & Lead Aktif", res.message)
        self.assertIn("Role Keywords", res.message)

        # 2. Update role
        res = self.handler.handle(TelegramRequest(chat_id=123, text="/filter role laravel, python"))
        self.assertTrue(res.success)
        self.assertIn("laravel, python", res.message)

        # 3. Add role
        res = self.handler.handle(TelegramRequest(chat_id=123, text="/filter addrole golang"))
        self.assertTrue(res.success)
        self.assertIn("golang", res.message)

        # 4. Update score
        res = self.handler.handle(TelegramRequest(chat_id=123, text="/filter score 0.5"))
        self.assertTrue(res.success)
        self.assertIn("0.50", res.message)

        # 5. Update age
        res = self.handler.handle(TelegramRequest(chat_id=123, text="/filter age 7"))
        self.assertTrue(res.success)
        self.assertIn("7 hari", res.message)

        # 6. Update bids
        res = self.handler.handle(TelegramRequest(chat_id=123, text="/filter bid 30"))
        self.assertTrue(res.success)
        self.assertIn("30 bid", res.message)

        # 7. Disable bids filter
        res = self.handler.handle(TelegramRequest(chat_id=123, text="/filter bid 0"))
        self.assertTrue(res.success)
        self.assertIn("dinonaktifkan", res.message)

        # 8. Reset filter
        res = self.handler.handle(TelegramRequest(chat_id=123, text="/filter reset"))
        self.assertTrue(res.success)
        self.assertIn("default", res.message)


if __name__ == "__main__":
    unittest.main()
