import io
import json
import sqlite3
import unittest
from unittest.mock import patch
from urllib.error import URLError

from bot_loker_wfh.bot import BotRunner
from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.drafts import DraftService
from bot_loker_wfh.pipeline import JobPipeline
from bot_loker_wfh.telegram_client import TelegramClient, TelegramError

from test_bot_pipeline import PROFILE, insert_job

OWNER = 111
STRANGER = 999


class FakeClient:
    def __init__(self):
        self.texts = []
        self.messages = []
        self.answers = []
        self.batches = []
        self.edits = []

    def edit_message_text(self, chat_id, message_id, text):
        self.edits.append((chat_id, message_id, text))

    def send_text(self, chat_id, text, keyboard=()):
        self.texts.append((chat_id, text))

    def send_message(self, message):
        self.messages.append(message)

    def answer_callback(self, query_id, text=""):
        self.answers.append((query_id, text))

    def get_updates(self, offset, *, timeout=30):
        if self.batches:
            batch = self.batches.pop(0)
            if isinstance(batch, BaseException):
                raise batch
            return batch
        raise KeyboardInterrupt


class FakeScheduler:
    def __init__(self):
        self.calls = 0

    def run_once(self):
        self.calls += 1
        return {"remoteok": 3}


def message_update(chat_id, text, update_id=1):
    return {"update_id": update_id, "message": {"chat": {"id": chat_id}, "text": text}}


def callback_update(chat_id, data, update_id=1):
    return {
        "update_id": update_id,
        "callback_query": {"id": "q1", "data": data, "message": {"chat": {"id": chat_id}}},
    }


class BotRunnerTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)
        insert_job(self.connection, 1, description="NestJS and React", status="CANDIDATE")
        self.client = FakeClient()
        self.scheduler = FakeScheduler()
        self.runner = BotRunner(
            self.connection,
            client=self.client,
            allowed_chat_ids=frozenset({OWNER}),
            draft_service=DraftService(self.connection, PROFILE),
            pipeline=JobPipeline(self.connection, PROFILE),
            scheduler=self.scheduler,
            interval_seconds=4 * 3600,
            sleep=lambda seconds: None,
        )

    def application_status(self):
        row = self.connection.execute("SELECT status FROM applications").fetchone()
        return row[0] if row else None

    def prepare_and_approve(self):
        self.runner.handle_update(callback_update(OWNER, "prepare:job-1:CANDIDATE"))
        application_id = self.connection.execute("SELECT id FROM applications").fetchone()[0]
        self.runner.handle_update(
            callback_update(OWNER, f"approve:{application_id}:PENDING_APPROVAL")
        )
        return application_id

    def test_stranger_is_rejected_and_nothing_changes(self):
        self.runner.handle_update(message_update(STRANGER, "/lowongan"))
        self.runner.handle_update(callback_update(STRANGER, "prepare:job-1:CANDIDATE"))

        self.assertEqual(self.client.texts, [(STRANGER, "Unauthorized chat.")])
        self.assertEqual(self.client.answers, [("q1", "Unauthorized chat.")])
        self.assertIsNone(self.application_status())

    def test_prepare_button_creates_draft_and_sends_review_buttons(self):
        self.runner.handle_update(callback_update(OWNER, "prepare:job-1:CANDIDATE"))

        self.assertEqual(self.application_status(), "PENDING_APPROVAL")
        message = self.client.messages[0]
        self.assertIn("Cover letter", message.text)
        labels = [button.label for button in message.inline_keyboard[0]]
        self.assertEqual(labels, ["Setujui", "Tolak"])

    def test_approve_sends_apply_link_and_replay_is_rejected(self):
        application_id = self.prepare_and_approve()

        self.assertEqual(self.application_status(), "APPROVED")
        follow_up = self.client.texts[-1][1]
        self.assertIn("https://example.com/1", follow_up)
        self.assertIn(f"/dilamar {application_id}", follow_up)

        self.runner.handle_update(
            callback_update(OWNER, f"approve:{application_id}:PENDING_APPROVAL")
        )
        self.assertEqual(self.client.answers[-1][1], "This approval request is no longer active.")
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM application_status_history "
                                    "WHERE to_status='APPROVED'").fetchone()[0],
            1,
        )

    def test_reject_command_with_id_prefix(self):
        self.runner.handle_update(message_update(OWNER, "/siapkan job-1"))
        application_id = self.connection.execute("SELECT id FROM applications").fetchone()[0]

        self.runner.handle_update(message_update(OWNER, f"/tolak {application_id[:8]}"))

        self.assertEqual(self.application_status(), "REJECTED_BY_USER")

    def test_dilamar_marks_submitted_only_from_approved(self):
        self.runner.handle_update(callback_update(OWNER, "prepare:job-1:CANDIDATE"))
        application_id = self.connection.execute("SELECT id FROM applications").fetchone()[0]

        self.runner.handle_update(message_update(OWNER, f"/dilamar {application_id}"))
        self.assertEqual(self.application_status(), "PENDING_APPROVAL")

        self.runner.handle_update(
            callback_update(OWNER, f"approve:{application_id}:PENDING_APPROVAL")
        )
        self.runner.handle_update(message_update(OWNER, f"/dilamar {application_id}"))

        self.assertEqual(self.application_status(), "SUBMITTED")
        row = self.connection.execute("SELECT method, submitted_at FROM applications").fetchone()
        self.assertEqual(row[0], "manual")
        self.assertIsNotNone(row[1])
        self.assertEqual(
            self.connection.execute(
                "SELECT to_status FROM application_status_history ORDER BY changed_at, rowid"
            ).fetchall()[-1][0],
            "SUBMITTED",
        )

    def test_help_and_unknown_commands(self):
        self.runner.handle_update(message_update(OWNER, "/start@MyBot"))
        self.runner.handle_update(message_update(OWNER, "/bogus"))

        self.assertIn("/siapkan", self.client.texts[0][1])
        self.assertIn("tidak dikenal", self.client.texts[1][1])

    def test_ambiguous_or_wildcard_id_prefix_is_not_resolved(self):
        insert_job(self.connection, 2, description="NestJS", status="CANDIDATE")

        self.assertIsNone(self.runner._resolve("jobs", ["job-"]))
        self.assertIsNone(self.runner._resolve("jobs", ["%"]))
        self.assertEqual(self.runner._resolve("jobs", ["job-1"]), "job-1")

    def test_notify_candidates_sends_each_candidate_once(self):
        self.assertEqual(self.runner.notify_candidates(), 1)
        self.assertEqual(self.runner.notify_candidates(), 0)
        self.assertEqual(len(self.client.messages), 1)
        self.assertIn("Siapkan draft", self.client.messages[0].inline_keyboard[0][0].label)

    def test_run_cycle_fetches_filters_and_notifies(self):
        insert_job(self.connection, 2, description="Python, NestJS and React", status="DISCOVERED")

        summary = self.runner.run_cycle()

        self.assertEqual(self.scheduler.calls, 1)
        self.assertEqual(summary["remoteok_inserted"], 3)
        self.assertEqual(summary["candidate"], 1)
        self.assertEqual(summary["notified"], 2)

    def test_run_forever_handles_updates_and_survives_poll_errors(self):
        self.client.batches = [
            TelegramError("boom"),
            [message_update(OWNER, "/help", update_id=7)],
        ]

        with self.assertRaises(KeyboardInterrupt):
            self.runner.run_forever()

        texts = [text for _, text in self.client.texts]
        self.assertTrue(texts[0].startswith("Bot aktif. Ketik /help untuk daftar perintah."))
        self.assertTrue(any("/siapkan" in text for text in texts))
        self.assertEqual(self.scheduler.calls, 1)


class TelegramClientTest(unittest.TestCase):
    def test_error_messages_never_contain_the_token(self):
        client = TelegramClient("SECRET-TOKEN")
        with patch("bot_loker_wfh.telegram_client.urlopen",
                   side_effect=URLError("https://api.telegram.org/botSECRET-TOKEN/x")):
            with self.assertRaises(TelegramError) as raised:
                client.send_text(1, "hi")
        self.assertNotIn("SECRET-TOKEN", str(raised.exception))

    def test_send_text_builds_inline_keyboard_and_truncates(self):
        captured = {}

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data)
            return Response(b'{"ok": true, "result": {}}')

        with patch("bot_loker_wfh.telegram_client.urlopen", fake_urlopen):
            TelegramClient("T").send_text(5, "x" * 9000, ((("Ok", "cb:1"),),))

        self.assertTrue(captured["url"].endswith("/botT/sendMessage"))
        self.assertEqual(len(captured["body"]["text"]), 4000)
        self.assertEqual(
            captured["body"]["reply_markup"]["inline_keyboard"],
            [[{"text": "Ok", "callback_data": "cb:1"}]],
        )

    def test_api_rejection_raises(self):
        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch("bot_loker_wfh.telegram_client.urlopen",
                   lambda request, timeout: Response(b'{"ok": false}')):
            with self.assertRaises(TelegramError):
                TelegramClient("T").answer_callback("1")


if __name__ == "__main__":
    unittest.main()
