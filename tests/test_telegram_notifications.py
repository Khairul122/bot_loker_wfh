import sqlite3
import unittest

from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.telegram_notifications import TelegramNotificationService


class TelegramNotificationTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)
        self.connection.execute(
            "INSERT INTO jobs (id, source, external_id, source_external_key, "
            "canonical_fingerprint, title, company, description, location, apply_url, "
            "status, filtered_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "job-candidate",
                "remoteok",
                "123",
                "remoteok:123",
                "candidate-fingerprint",
                "Backend Developer",
                "Acme Inc.",
                "Fully remote backend role.",
                "Worldwide",
                "https://example.com/jobs/123",
                "CANDIDATE",
                None,
            ),
        )
        self.connection.execute(
            "INSERT INTO applications (id, job_id, idempotency_key, status, "
            "cover_letter, cv_summary, method) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "application-pending",
                "job-candidate",
                "application-key",
                "PENDING_APPROVAL",
                "Cover letter for Acme",
                "Relevant CV summary",
                "manual",
            ),
        )
        self.connection.commit()
        self.service = TelegramNotificationService(self.connection, chat_id=123)

    def tearDown(self):
        self.connection.close()

    def test_candidate_notification_contains_summary_and_prepare_button(self):
        messages = self.service.candidate_notifications()

        self.assertEqual(len(messages), 1)
        message = messages[0]
        self.assertEqual(message.chat_id, 123)
        self.assertIn("Backend Developer", message.text)
        self.assertIn("Acme Inc.", message.text)
        self.assertIn("Worldwide", message.text)
        self.assertIn("remoteok", message.text)
        self.assertIn("https://example.com/jobs/123", message.text)
        self.assertEqual(message.inline_keyboard[0][0].label, "Siapkan draft")
        self.assertEqual(
            message.inline_keyboard[0][0].callback_data,
            "prepare:job-candidate:CANDIDATE",
        )

    def test_pending_approval_notification_has_idempotent_callbacks(self):
        messages = self.service.pending_approval_notifications()

        self.assertEqual(len(messages), 1)
        message = messages[0]
        buttons = message.inline_keyboard[0]
        self.assertEqual(buttons[0].label, "Setujui")
        self.assertEqual(buttons[1].label, "Tolak")
        self.assertEqual(
            buttons[0].callback_data,
            "approve:application-pending:PENDING_APPROVAL",
        )
        self.assertEqual(
            buttons[1].callback_data,
            "reject:application-pending:PENDING_APPROVAL",
        )
        self.assertIn("Cover letter for Acme", message.text)

    def test_candidate_with_filtered_reason_includes_reason(self):
        self.connection.execute(
            "UPDATE jobs SET filtered_reason = ? WHERE id = ?",
            ("manual review note", "job-candidate"),
        )
        self.connection.commit()

        message = self.service.candidate_notifications()[0]

        self.assertIn("manual review note", message.text)


if __name__ == "__main__":
    unittest.main()
