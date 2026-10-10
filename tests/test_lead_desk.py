from bot_loker_wfh import database
import tempfile
import threading
import unittest
from pathlib import Path

from bot_loker_wfh.cv_profile import SafeCvProfile
from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.lead_desk import RevisionFailed, approve_lead, draft_proposal, get_bid_terms, list_leads, set_lead_status
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
        self.connection = database.connect()
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
        self.connection = database.connect()
        apply_schema(self.connection)
        insert_lead(self.connection, "a")
        self.spawned = []
        self.work = OfficeWork(hunters={}, draft_service_for=None, form_assist_enabled=True, interval_seconds=1,
            lock=threading.Lock(),
            proposal_writer=lambda connection, lead_id, mark_interested=True, note="": draft_proposal(
                connection, lead_id, PROFILE, mark_interested=mark_interested, note=note),
            spawn=lambda cmd, **kwargs: self.spawned.append(cmd),
        )

    def tearDown(self):
        self.connection.close()
        self.tmp.cleanup()

    def test_fill_needs_a_proposal_then_starts_browsermcp(self):
        self.assertEqual(self.work.lead_action(self.connection, "a", "fill", {})["mode"], "manual")
        self.assertEqual(self.spawned, [])

        self.work.lead_action(self.connection, "a", "proposal", {"text": "My edited bid"})
        result = self.work.lead_action(self.connection, "a", "fill", {})

        self.assertEqual(result["mode"], "form")
        self.assertEqual(self.spawned[0][-2:], ["--lead-id", "a"])
        self.assertNotIn("--submit-bid", self.spawned[0])
        self.assertEqual(
            self.connection.execute("SELECT proposal FROM leads WHERE id = 'a'").fetchone()[0], "My edited bid"
        )


TERMS_JSON = '{"hourly_rate": "25", "weekly_limit": "30", "duration_days": "14", "milestones": "API, tests, handover"}'


class BidFlowTest(unittest.TestCase):
    """Cora drafts, the owner revises and approves, Faris submits (the spawn is faked)."""

    def setUp(self):
        self.connection = database.connect()
        apply_schema(self.connection)
        self.spawned = []
        self.calls = []

        def llm(prompt):
            self.calls.append(prompt)
            return TERMS_JSON if prompt.startswith("Return JSON only") else "Revised proposal " + "x" * 120

        self.work = OfficeWork(hunters={}, draft_service_for=None, form_assist_enabled=True, interval_seconds=1,
            lock=threading.Lock(),
            proposal_writer=lambda connection, lead_id, mark_interested=True, note="": draft_proposal(
                connection, lead_id, PROFILE, llm, mark_interested=mark_interested, note=note),
            spawn=lambda cmd, **kwargs: self.spawned.append(cmd))

    def test_draft_stores_suggested_bid_terms(self):
        insert_lead(self.connection, "a")
        result = self.work.lead_action(self.connection, "a", "proposal", {})
        self.assertEqual(result["bid_terms"]["duration_days"], "14")
        self.assertEqual(get_bid_terms(self.connection, "a").hourly_rate, "25")
        self.assertEqual(list_leads(self.connection)[0]["bid_terms"]["weekly_limit"], "30")

    def test_revise_sends_the_note_and_replaces_the_draft(self):
        insert_lead(self.connection, "a")
        self.work.lead_action(self.connection, "a", "proposal", {})
        result = self.work.lead_action(self.connection, "a", "revise", {"note": "lebih singkat"})
        self.assertTrue(result["revised"])
        self.assertTrue(any("lebih singkat" in call for call in self.calls))
        self.assertTrue(self.connection.execute("SELECT proposal FROM leads WHERE id='a'").fetchone()[0].startswith("Revised"))
        with self.assertRaises(ValueError):
            self.work.lead_action(self.connection, "a", "revise", {"note": " "})

    def test_failed_revision_keeps_the_old_draft(self):
        insert_lead(self.connection, "a")
        draft_proposal(self.connection, "a", PROFILE)
        old = self.connection.execute("SELECT proposal FROM leads WHERE id='a'").fetchone()[0]
        with self.assertRaises(RevisionFailed):
            draft_proposal(self.connection, "a", PROFILE, lambda prompt: "", note="ubah")
        self.assertEqual(self.connection.execute("SELECT proposal FROM leads WHERE id='a'").fetchone()[0], old)

    def test_approve_marks_approved_and_starts_the_submitting_filler(self):
        insert_lead(self.connection, "a", source="freelancer")
        self.connection.execute("UPDATE leads SET url = 'https://www.freelancer.com/projects/x' WHERE id = 'a'")
        self.work.lead_action(self.connection, "a", "proposal", {"text": "p" * 120})
        result = self.work.lead_action(self.connection, "a", "approve", {})
        self.assertEqual((result["mode"], result["status"]), ("submitting", "APPROVED"))
        self.assertEqual(self.spawned[0][-4:], ["--lead-id", "a", "--submit-bid", "--approved"])
        self.assertEqual(self.connection.execute("SELECT status FROM leads WHERE id='a'").fetchone()[0], "APPROVED")

    def test_approve_refuses_unsafe_cases(self):
        insert_lead(self.connection, "short")
        self.connection.execute("UPDATE leads SET url = 'https://www.freelancer.com/projects/x', proposal = 'tiny' WHERE id = 'short'")
        with self.assertRaises(ValueError):
            approve_lead(self.connection, "short")  # proposal too short
        insert_lead(self.connection, "other")
        self.connection.execute("UPDATE leads SET proposal = ? WHERE id = 'other'", ("p" * 120,))
        with self.assertRaises(ValueError):
            approve_lead(self.connection, "other")  # example.com is not an allowed platform
        insert_lead(self.connection, "ign", status="IGNORED")
        self.connection.execute("UPDATE leads SET url = 'https://www.freelancer.com/p', proposal = ? WHERE id = 'ign'", ("p" * 120,))
        with self.assertRaises(ValueError):
            approve_lead(self.connection, "ign")
        self.assertEqual(self.spawned, [])

    def test_newest_project_comes_before_older_drafted_ones(self):
        insert_lead(self.connection, "old")
        insert_lead(self.connection, "new")
        self.connection.execute("UPDATE leads SET posted_at = '2026-01-01T00:00:00+00:00', proposal = 'draft' WHERE id = 'old'")
        self.connection.execute("UPDATE leads SET posted_at = '2026-10-10T09:02:21+07:00' WHERE id = 'new'")
        self.assertEqual([l["id"] for l in list_leads(self.connection)], ["new", "old"])


class AutoProposalTest(unittest.TestCase):
    def test_cycle_drafts_best_new_leads_without_marking_interest(self):
        connection = database.connect()
        apply_schema(connection)
        insert_lead(connection, "low")
        insert_lead(connection, "high")
        insert_lead(connection, "seen", status="IGNORED")
        connection.execute("UPDATE leads SET score = 0.9 WHERE id = 'high'")
        portfolio = {"repos": [{"name": "laravel-api", "url": "https://github.com/u/laravel-api",
                                "language": "PHP", "description": "", "topics": []}]}
        work = OfficeWork(hunters={}, draft_service_for=None, form_assist_enabled=False,
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
        self.connection = database.connect()
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


class NineRouterRunnableTest(unittest.TestCase):
    def test_9router_is_the_only_provider_and_template_falls_back(self):
        from bot_loker_wfh.llm import (
            LLMError,
            LLMRouter,
            OpenAICompatibleProvider,
            create_llm_from_settings,
        )
        from bot_loker_wfh.config import Settings

        for legacy in ("anthropic", "opencode", "9router", ""):
            settings = Settings.from_environment({"LLM_PROVIDER": legacy})
            self.assertEqual(settings.llm_provider, "9router")
            router = create_llm_from_settings(settings)
            self.assertIsInstance(router, LLMRouter)
            provider = router.chain[0][0]
            self.assertIsInstance(provider, OpenAICompatibleProvider)

        # draft callers fall back to the template when 9Router raises
        def failing(prompt):
            raise LLMError("all_providers_failed")

        self.assertEqual(_template_fallback(failing, "fallback"), "fallback")


def _template_fallback(provider, default):
    from bot_loker_wfh.llm import LLMError
    try:
        return provider("x") or default
    except LLMError:
        return default
