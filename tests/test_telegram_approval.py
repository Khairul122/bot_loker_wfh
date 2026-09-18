import sqlite3
import unittest

from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.telegram_approval import TelegramApprovalHandler
from bot_loker_wfh.telegram_auth import TelegramAuth, TelegramRequest


class TelegramApprovalHandlerTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)
        self.connection.execute(
            "INSERT INTO jobs (id, source, external_id, source_external_key, "
            "canonical_fingerprint, title, company, description, apply_url) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ? ,?)",
            ("job-approval", "remoteok", "123", "remoteok:123", "approval-fp", "Backend Developer", "Acme", "x", "https://example.com/job"),
        )
        self.connection.execute(
            "INSERT INTO applications (id, job_id, idempotency_key, status, cover_letter, cv_summary) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("application-approval", "job-approval", "approval-key", "PENDING_APPROVAL", "Cover", "CV"),
        )
        self.connection.commit()
        self.handler = TelegramApprovalHandler(
            self.connection,
            auth=TelegramAuth(allowed_chat_ids=frozenset({123})),
        )

    def tearDown(self):
        self.connection.close()

    def test_approve_changes_status_and_records_history(self):
        result = self.handler.handle(
            TelegramRequest(chat_id=123, callback_data="approve:application-approval:PENDING_APPROVAL")
        )

        self.assertTrue(result.success)
        self.assertEqual(result.message, "Application approved.")
        self.assertEqual(
            self.connection.execute(
                "SELECT status FROM applications WHERE id = 'application-approval'"
            ).fetchone()[0],
            "APPROVED",
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT from_status, to_status, changed_by FROM application_status_history"
            ).fetchone(),
            ("PENDING_APPROVAL", "APPROVED", "user"),
        )

    def test_reject_changes_status_and_records_history(self):
        result = self.handler.handle(
            TelegramRequest(chat_id=123, callback_data="reject:application-approval:PENDING_APPROVAL")
        )

        self.assertTrue(result.success)
        self.assertEqual(result.message, "Application rejected.")
        self.assertEqual(
            self.connection.execute(
                "SELECT status FROM applications WHERE id = 'application-approval'"
            ).fetchone()[0],
            "REJECTED_BY_USER",
        )

    def test_double_click_is_rejected_without_second_history_row(self):
        callback = TelegramRequest(
            chat_id=123,
            callback_data="approve:application-approval:PENDING_APPROVAL",
        )

        self.assertTrue(self.handler.handle(callback).success)
        result = self.handler.handle(callback)

        self.assertFalse(result.success)
        self.assertEqual(result.message, "This approval request is no longer active.")
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM application_status_history"
            ).fetchone()[0],
            1,
        )

    def test_unauthorized_callback_is_rejected_without_data_change(self):
        result = self.handler.handle(
            TelegramRequest(chat_id=999, callback_data="approve:application-approval:PENDING_APPROVAL")
        )

        self.assertFalse(result.success)
        self.assertEqual(result.message, "Unauthorized chat.")
        self.assertEqual(
            self.connection.execute(
                "SELECT status FROM applications WHERE id = 'application-approval'"
            ).fetchone()[0],
            "PENDING_APPROVAL",
        )

    def test_malformed_callback_is_rejected_safely(self):
        result = self.handler.handle(
            TelegramRequest(chat_id=123, callback_data="approve:missing-status")
        )

        self.assertFalse(result.success)
        self.assertEqual(result.message, "Invalid approval request.")


if __name__ == "__main__":
    unittest.main()
