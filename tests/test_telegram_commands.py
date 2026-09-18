import sqlite3
import unittest

from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.telegram_auth import TelegramAuth, TelegramRequest
from bot_loker_wfh.telegram_commands import TelegramCommandHandler


class TelegramCommandHandlerTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
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
        self.assertIn("Lowongan ditemukan: 3", result.message)
        self.assertIn("Lolos filter: 1", result.message)
        self.assertIn("Dilamar: 1", result.message)
        self.assertIn("Mendapat respons: 0", result.message)

    def test_unknown_or_malformed_command_is_rejected(self):
        result = self.handler.handle(TelegramRequest(chat_id=123, text="/status"))

        self.assertFalse(result.success)
        self.assertEqual(result.message, "Usage: /status [application_id] [status]")

    def test_unauthorized_command_is_rejected(self):
        result = self.handler.handle(TelegramRequest(chat_id=999, text="/laporan"))

        self.assertFalse(result.success)
        self.assertEqual(result.message, "Unauthorized chat.")


if __name__ == "__main__":
    unittest.main()
