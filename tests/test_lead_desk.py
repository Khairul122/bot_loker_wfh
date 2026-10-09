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


class AutoProposalTest(unittest.TestCase):
    def test_cycle_drafts_best_new_leads_without_marking_interest(self):
        connection = sqlite3.connect(":memory:")
        apply_schema(connection)
        insert_lead(connection, "low")
        insert_lead(connection, "high")
        insert_lead(connection, "seen", status="IGNORED")
        connection.execute("UPDATE leads SET score = 0.9 WHERE id = 'high'")
        portfolio = {"repos": [{"name": "laravel-api", "url": "https://github.com/u/laravel-api",
                                "language": "PHP", "description": "", "topics": []}]}
        work = OfficeWork(
            Path("unused.db"), hunters={}, draft_service_for=None, form_assist_enabled=False,
            interval_seconds=1, lock=threading.Lock(),
            proposal_writer=lambda c, lead_id, mark_interested=True: draft_proposal(
                c, lead_id, PROFILE, portfolio=portfolio, mark_interested=mark_interested),
        )

        self.assertEqual(work.draft_proposals(connection, limit=1), 1)
        status, proposal = connection.execute("SELECT status, proposal FROM leads WHERE id = 'high'").fetchone()

        self.assertEqual(status, "NEW")
        self.assertIn("https://github.com/u/laravel-api", proposal)
        self.assertEqual(work.draft_proposals(connection, limit=5), 1)  # only "low" left


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


class LanguageAndCommentTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)

    def test_language_follows_post_text_not_source(self):
        from bot_loker_wfh.lead_desk import is_indonesian

        self.assertTrue(is_indonesian(
            "Dibutuhkan programmer untuk pembuatan aplikasi kasir berbasis web dengan Laravel", "freelancer"))
        self.assertFalse(is_indonesian(
            "We need an experienced developer to build a booking web app with React and Laravel",
            "projects.co.id"))

    def test_indonesian_post_on_freelancer_gets_indonesian_bid_and_comment(self):
        from bot_loker_wfh.lead_desk import draft_comment

        self.connection.execute(
            "INSERT INTO leads (id, source, external_id, kind, title, description, url) VALUES "
            "('x', 'freelancer', 'x', 'project', 'Aplikasi kasir', "
            "'Saya butuh pembuatan aplikasi kasir untuk toko dengan laporan harian yang bisa dicetak', 'u')"
        )
        portfolio = {"repos": [{"name": "aplikasi-kasir", "url": "https://github.com/Khairul122/aplikasi-kasir",
                                "language": "PHP", "description": "", "topics": []}]}
        prompts = []

        proposal = draft_proposal(self.connection, "x", PROFILE, lambda p: prompts.append(p) or "", portfolio)
        comment = draft_comment(self.connection, "x", None, portfolio)

        self.assertTrue(proposal.startswith("Halo"))
        self.assertIn("Bahasa Indonesia", prompts[0])
        self.assertIn("PHP (1 repos)", prompts[0])
        self.assertIn("github.com/Khairul122/aplikasi-kasir", comment)
        self.assertEqual(self.connection.execute("SELECT comment FROM leads WHERE id='x'").fetchone()[0], comment)


class OpenCodeProviderTest(unittest.TestCase):
    def test_runs_opencode_with_prompt_file_outside_repo(self):
        from bot_loker_wfh.llm import LLMError, OpenCodeProvider

        seen = {}

        class Done:
            returncode, stdout = 0, "  a bid  \n"

        def fake_run(cmd, cwd, **kwargs):
            seen["cmd"], seen["prompt"] = cmd, Path(cmd[6]).read_text(encoding="utf-8")
            return Done()

        provider = OpenCodeProvider("9router/ComboOpenCode", run=fake_run)
        self.assertEqual(provider("line1\nline2"), "a bid")
        self.assertEqual(seen["cmd"][1:6], ["run", "-m", "9router/ComboOpenCode", "-f"])
        self.assertEqual(seen["prompt"], "line1\nline2")

        Done.returncode = 1
        with self.assertRaises(LLMError):
            provider("x")
