import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from bot_loker_wfh.cv_profile import SafeCvProfile
from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.lead_desk import draft_proposal, list_leads, set_lead_status
from bot_loker_wfh.office_work import OfficeWork

PROFILE = SafeCvProfile.from_values(skills=["Laravel", "Flutter"])


def insert_lead(connection, lead_id, source="freelancer", status="NEW"):
    connection.execute(
        "INSERT INTO leads (id, source, external_id, kind, title, description, url, budget, status) "
        "VALUES (?, ?, ?, 'project', 'Build API', 'Need a Laravel API', 'https://example.com/p', '$200', ?)",
        (lead_id, source, lead_id, status),
    )


class LeadDeskTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)

    def test_template_proposal_language_follows_source_and_marks_interest(self):
        insert_lead(self.connection, "en")
        insert_lead(self.connection, "id", source="projects.co.id")

        english = draft_proposal(self.connection, "en", PROFILE)
        indonesian = draft_proposal(self.connection, "id", PROFILE)

        self.assertIn("Laravel", english)
        self.assertTrue(english.startswith("Hi"))
        self.assertTrue(indonesian.startswith("Halo"))
        self.assertEqual(
            self.connection.execute("SELECT status, proposal FROM leads WHERE id = 'en'").fetchone(),
            ("INTERESTED", english),
        )

    def test_llm_failure_falls_back_to_template(self):
        insert_lead(self.connection, "a")

        def broken(prompt):
            raise TimeoutError

        self.assertIn("Build API", draft_proposal(self.connection, "a", PROFILE, broken))

    def test_ignored_leads_disappear_and_unknown_status_is_refused(self):
        insert_lead(self.connection, "a")
        insert_lead(self.connection, "b")
        set_lead_status(self.connection, "b", "IGNORED")

        self.assertEqual([lead["id"] for lead in list_leads(self.connection)], ["a"])
        with self.assertRaises(ValueError):
            set_lead_status(self.connection, "a", "APPLIED")
        with self.assertRaises(KeyError):
            set_lead_status(self.connection, "missing", "IGNORED")


class LeadFillTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db = Path(self.tmp.name) / "app.db"
        self.connection = sqlite3.connect(db)
        apply_schema(self.connection)
        insert_lead(self.connection, "a")
        self.spawned = []
        self.work = OfficeWork(
            db, hunters={}, draft_service_for=None, form_assist_enabled=True, interval_seconds=1,
            lock=threading.Lock(),
            proposal_writer=lambda connection, lead_id: draft_proposal(connection, lead_id, PROFILE),
            spawn=lambda cmd, **kwargs: self.spawned.append(cmd),
        )

    def tearDown(self):
        self.connection.close()
        self.tmp.cleanup()

    def test_fill_needs_a_proposal_then_starts_the_chosen_browser(self):
        self.assertEqual(self.work.lead_action(self.connection, "a", "fill", {})["mode"], "manual")
        self.assertEqual(self.spawned, [])

        self.work.lead_action(self.connection, "a", "proposal", {"text": "My edited bid"})
        result = self.work.lead_action(self.connection, "a", "fill", {"engine": "playwright"})

        self.assertEqual((result["mode"], result["engine"]), ("form", "playwright"))
        self.assertEqual(self.spawned[0][-4:], ["--lead-id", "a", "--engine", "playwright"])
        self.assertEqual(
            self.connection.execute("SELECT proposal FROM leads WHERE id = 'a'").fetchone()[0], "My edited bid"
        )


class LoginWaitTest(unittest.TestCase):
    def test_waits_until_the_login_link_is_gone_and_stops_when_browser_closes(self):
        from bot_loker_wfh.form_agent.agent import LOGIN_GATE, FormAgent

        class FakeClient:
            def __init__(self, pages):
                self.pages = list(pages)

            def peek_snapshot(self):
                return self.pages.pop(0) if self.pages else None

        logged_out = '- link "Log In" [ref=e40]'
        self.assertTrue(LOGIN_GATE.search(logged_out))
        self.assertTrue(FormAgent._wait_for_login(
            FakeClient([logged_out, '- textbox "Bid amount" [ref=e9]']), 5, poll_seconds=0))
        self.assertFalse(FormAgent._wait_for_login(FakeClient([logged_out]), 5, poll_seconds=0))


if __name__ == "__main__":
    unittest.main()
