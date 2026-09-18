import unittest

from bot_loker_wfh.config import Settings
from bot_loker_wfh.telegram_auth import TelegramAuth, TelegramRequest


class TelegramAuthTest(unittest.TestCase):
    def test_settings_load_token_and_allowlisted_chat_ids_from_environment(self):
        settings = Settings.from_environment(
            {
                "TELEGRAM_BOT_TOKEN": "secret-token",
                "TELEGRAM_ALLOWED_CHAT_IDS": "123, 456",
            }
        )

        self.assertEqual(settings.telegram_bot_token, "secret-token")
        self.assertEqual(settings.telegram_allowed_chat_ids, frozenset({123, 456}))

    def test_invalid_chat_id_configuration_fails_clearly(self):
        with self.assertRaises(ValueError):
            Settings.from_environment({"TELEGRAM_ALLOWED_CHAT_IDS": "not-a-number"})

    def test_authorized_request_is_accepted(self):
        auth = TelegramAuth(allowed_chat_ids=frozenset({123}))

        decision = auth.authorize(TelegramRequest(chat_id=123, text="/lowongan"))

        self.assertTrue(decision.allowed)
        self.assertIsNone(decision.safe_response)

    def test_unauthorized_request_is_rejected_with_safe_response(self):
        auth = TelegramAuth(allowed_chat_ids=frozenset({123}))

        decision = auth.authorize(
            TelegramRequest(chat_id=999, text="/status application-1 APPROVED")
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.safe_response, "Unauthorized chat.")
        self.assertNotIn("application-1", decision.safe_response)
        self.assertNotIn("APPROVED", decision.safe_response)

    def test_empty_allowlist_rejects_everything(self):
        auth = TelegramAuth(allowed_chat_ids=frozenset())

        decision = auth.authorize(TelegramRequest(chat_id=123, text="/lowongan"))

        self.assertFalse(decision.allowed)


if __name__ == "__main__":
    unittest.main()
