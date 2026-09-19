import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from bot_loker_wfh import form_assist
from bot_loker_wfh.bot import BotRunner
from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.drafts import DraftService
from bot_loker_wfh.form_assist import (
    Applicant,
    FormAssistError,
    ats_for_url,
    fill_page,
    load_answers,
    load_applicant,
    resolve_form_target,
)
from bot_loker_wfh.pipeline import JobPipeline

from test_bot_pipeline import PROFILE, insert_job
from test_bot_runner import OWNER, FakeClient, callback_update, message_update

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

GREENHOUSE_HTML = """
<form onsubmit="window.__submitted = true; return false;">
  <label for="first_name">First Name*</label><input id="first_name" required>
  <label for="last_name">Last Name*</label><input id="last_name" required>
  <label for="preferred_name">Preferred First Name</label><input id="preferred_name">
  <label for="email">Email*</label><input id="email" required>
  <label for="phone">Phone*</label><input id="phone" type="tel" required>
  <label for="resume">Resume</label><input id="resume" type="file">
  <label for="cover_letter">Cover Letter</label><input id="cover_letter" type="file">
  <label for="q1">LinkedIn Profile</label><input id="q1">
  <label for="q2">Expected salary*</label><input id="q2" required>
  <label for="q3">Are you eligible to work here?*</label>
  <input id="q3" role="combobox" aria-required="true">
  <button type="submit">Submit application</button>
</form>
"""

LEVER_HTML = """
<form onsubmit="window.__submitted = true; return false;">
  <input type="file" name="resume">
  <input name="name" required><input name="email" required><input name="phone">
  <input name="urls[LinkedIn]"><input name="urls[GitHub]">
  <textarea name="comments"></textarea>
  <ul><li class="application-question">
    <div class="application-label">What is your notice period? ✱</div>
    <textarea name="cards[1][field0]" required></textarea>
  </li></ul>
  <iframe src="https://hcaptcha.test/frame"></iframe>
  <button type="submit">Submit application</button>
</form>
"""


class FormAssistPureTest(unittest.TestCase):
    def test_ats_allowlist_is_exact_and_https_only(self):
        self.assertEqual(ats_for_url("https://job-boards.greenhouse.io/acme/jobs/1"), "greenhouse")
        self.assertEqual(ats_for_url("https://jobs.lever.co/acme/1/apply"), "lever")
        self.assertIsNone(ats_for_url("http://jobs.lever.co/acme/1"))
        self.assertIsNone(ats_for_url("https://evil.jobs.lever.co.attacker.com/x"))
        self.assertIsNone(ats_for_url("https://remoteok.com/remote-jobs/1"))

    def test_load_applicant_requires_core_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a.json"
            path.write_text(json.dumps({"first_name": "A", "last_name": "B"}), encoding="utf-8")
            with self.assertRaises(FormAssistError):
                load_applicant(path)
            path.write_text(
                json.dumps({"first_name": "A", "last_name": "B", "email": "a@b.co"}),
                encoding="utf-8",
            )
            self.assertEqual(load_applicant(path).full_name, "A B")
            with self.assertRaises(FormAssistError):
                load_applicant(Path(directory) / "missing.json")

    def test_load_answers_ignores_blank_values_and_missing_file(self):
        self.assertEqual(load_answers("nope.json"), {})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "answers.json"
            path.write_text('{"Salary": "Negotiable", "Empty": " "}', encoding="utf-8")
            self.assertEqual(load_answers(path), {"Salary": "Negotiable"})


class ResolveTargetTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)

    def add_application(self, number, *, source, apply_url, company="Acme"):
        insert_job(self.connection, number, source=source, status="CANDIDATE")
        self.connection.execute(
            "UPDATE jobs SET apply_url = ?, company = ?, external_id = ? WHERE id = ?",
            (apply_url, company, f"ext{number}", f"job-{number}"),
        )
        self.connection.execute(
            "INSERT INTO applications (id, job_id, idempotency_key, cover_letter, cv_summary, status) "
            "VALUES (?, ?, ?, 'letter', 'cv', 'APPROVED')",
            (f"app-{number}", f"job-{number}", f"key-{number}"),
        )
        self.connection.commit()
        return f"app-{number}"

    def test_greenhouse_uses_direct_board_url_even_for_company_hosted_pages(self):
        self.connection.execute(
            "INSERT INTO companies_ats (id, company_name, ats_type, ats_slug) "
            "VALUES ('c', 'Acme', 'greenhouse', 'acme')"
        )
        application = self.add_application(
            1, source="greenhouse", apply_url="https://acme.com/careers?gh_jid=ext1"
        )
        ats, url, letter, _ = resolve_form_target(self.connection, application)
        self.assertEqual(
            (ats, url, letter),
            ("greenhouse", "https://job-boards.greenhouse.io/acme/jobs/ext1", "letter"),
        )

    def test_lever_uses_stored_apply_url(self):
        application = self.add_application(
            2, source="lever", apply_url="https://jobs.lever.co/acme/abc/apply"
        )
        self.assertEqual(
            resolve_form_target(self.connection, application)[:2],
            ("lever", "https://jobs.lever.co/acme/abc/apply"),
        )

    def test_other_sources_are_reported_as_unsupported(self):
        application = self.add_application(
            3, source="remoteok", apply_url="https://remoteok.com/remote-jobs/3"
        )
        with self.assertRaises(FormAssistError) as raised:
            resolve_form_target(self.connection, application)
        self.assertIn("https://remoteok.com/remote-jobs/3", str(raised.exception))
        with self.assertRaises(FormAssistError):
            resolve_form_target(self.connection, "missing")


@unittest.skipIf(sync_playwright is None, "playwright is not installed")
class FormAssistBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except Exception as error:  # chromium not downloaded
            cls.playwright.stop()
            raise unittest.SkipTest(f"chromium unavailable: {error}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.resume = Path(self.directory.name) / "cv.pdf"
        self.resume.write_bytes(b"%PDF-1.4 test")
        self.applicant = Applicant(
            first_name="Khairul", last_name="Huda", email="me@example.com",
            phone="", resume_path=str(self.resume), linkedin="https://linkedin.com/in/me",
        )
        self.page = self.browser.new_page()
        self.page.route(
            "https://hcaptcha.test/**",
            lambda route: route.fulfill(body="<html></html>", content_type="text/html"),
        )
        self._patched = form_assist.LEVER_RESUME_PARSE_SECONDS
        form_assist.LEVER_RESUME_PARSE_SECONDS = 0

    def tearDown(self):
        form_assist.LEVER_RESUME_PARSE_SECONDS = self._patched
        self.page.close()
        self.directory.cleanup()

    def submitted(self):
        return self.page.evaluate("() => window.__submitted === true")

    def test_greenhouse_fields_are_filled_and_form_is_never_submitted(self):
        self.page.set_content(GREENHOUSE_HTML)

        report = fill_page(self.page, "greenhouse", self.applicant, "My letter", {})

        self.assertEqual(self.page.input_value("#first_name"), "Khairul")
        self.assertEqual(self.page.input_value("#last_name"), "Huda")
        self.assertEqual(self.page.input_value("#email"), "me@example.com")
        self.assertEqual(self.page.input_value("#preferred_name"), "")
        self.assertEqual(self.page.input_value("#q1"), "https://linkedin.com/in/me")
        self.assertEqual(self.page.evaluate("() => document.querySelector('#resume').files[0].name"), "cv.pdf")
        self.assertEqual(
            self.page.evaluate("() => document.querySelector('#cover_letter').files[0].name"),
            "cover_letter.txt",
        )
        self.assertFalse(self.submitted())
        self.assertEqual(
            report.filled,
            ["First Name", "Last Name", "Email", "Resume", "Cover letter", "LinkedIn"],
        )

    def test_unknown_required_fields_and_empty_phone_are_left_for_the_user(self):
        self.page.set_content(GREENHOUSE_HTML)

        report = fill_page(self.page, "greenhouse", self.applicant, "letter", {})

        self.assertEqual(
            report.needs_manual,
            ["Phone", "Expected salary", "Are you eligible to work here?"],
        )
        self.assertEqual(self.page.input_value("#phone"), "")
        self.assertEqual(self.page.input_value("#q2"), "")

    def test_reviewed_answers_fill_only_uniquely_matched_text_fields(self):
        self.page.set_content(GREENHOUSE_HTML)
        answers = {
            "Expected salary": "Negotiable",        # unique text field -> filled
            "First Name": "SHOULD NOT WIN",          # matches two fields -> skipped
            "eligible to work": "Yes",               # combobox -> never guessed
        }

        report = fill_page(self.page, "greenhouse", self.applicant, "letter", answers)

        self.assertEqual(self.page.input_value("#q2"), "Negotiable")
        self.assertEqual(self.page.input_value("#first_name"), "Khairul")
        self.assertEqual(self.page.input_value("#q3"), "")
        self.assertIn("Expected salary", report.filled)
        self.assertIn("Are you eligible to work here?", report.needs_manual)

    def test_lever_fields_captcha_and_custom_question_are_reported(self):
        self.page.set_content(LEVER_HTML)
        self.page.wait_for_timeout(300)

        report = fill_page(self.page, "lever", self.applicant, "My letter", {})

        self.assertEqual(self.page.input_value("input[name=name]"), "Khairul Huda")
        self.assertEqual(self.page.input_value("input[name=email]"), "me@example.com")
        self.assertEqual(self.page.input_value("input[name='urls[LinkedIn]']"), "https://linkedin.com/in/me")
        self.assertEqual(self.page.input_value("textarea[name=comments]"), "My letter")
        self.assertTrue(report.captcha)
        self.assertEqual(report.needs_manual, ["What is your notice period?"])
        self.assertFalse(self.submitted())

    def test_missing_resume_file_is_skipped_not_fatal(self):
        self.page.set_content(GREENHOUSE_HTML)
        applicant = Applicant("A", "B", "a@b.co", resume_path="does-not-exist.pdf")

        report = fill_page(self.page, "greenhouse", applicant, "", {})

        self.assertNotIn("Resume", report.filled)
        self.assertNotIn("Cover letter", report.filled)


class BotFillFormTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)
        self.connection.execute(
            "INSERT INTO companies_ats (id, company_name, ats_type, ats_slug) "
            "VALUES ('c', 'Acme', 'greenhouse', 'acme')"
        )
        insert_job(self.connection, 1, source="greenhouse", description="NestJS and React",
                   status="CANDIDATE")
        self.connection.execute("UPDATE jobs SET external_id = '99' WHERE id = 'job-1'")
        self.connection.commit()
        self.client = FakeClient()
        self.spawned = []

    def runner(self, *, enabled):
        return BotRunner(
            self.connection,
            client=self.client,
            allowed_chat_ids=frozenset({OWNER}),
            draft_service=DraftService(self.connection, PROFILE),
            pipeline=JobPipeline(self.connection, PROFILE),
            scheduler=None,
            interval_seconds=4 * 3600,
            form_assist_enabled=enabled,
            spawn=lambda command, **kwargs: self.spawned.append(command),
        )

    def approve(self, runner):
        runner.handle_update(callback_update(OWNER, "prepare:job-1:CANDIDATE"))
        application_id = self.connection.execute("SELECT id FROM applications").fetchone()[0]
        runner.handle_update(callback_update(OWNER, f"approve:{application_id}:PENDING_APPROVAL"))
        return application_id

    def test_disabled_feature_explains_and_spawns_nothing(self):
        runner = self.runner(enabled=False)
        application_id = self.approve(runner)

        runner.handle_update(message_update(OWNER, f"/isi {application_id}"))

        self.assertEqual(self.spawned, [])
        self.assertIn("FORM_ASSIST_ENABLED", self.client.texts[-1][1])

    def test_requires_approved_status(self):
        runner = self.runner(enabled=True)
        runner.handle_update(callback_update(OWNER, "prepare:job-1:CANDIDATE"))
        application_id = self.connection.execute("SELECT id FROM applications").fetchone()[0]

        runner.handle_update(message_update(OWNER, f"/isi {application_id}"))

        self.assertEqual(self.spawned, [])
        self.assertIn("APPROVED", self.client.texts[-1][1])

    def test_approved_application_spawns_fill_form_process(self):
        runner = self.runner(enabled=True)
        application_id = self.approve(runner)

        runner.handle_update(message_update(OWNER, f"/isi {application_id[:8]}"))

        self.assertEqual(len(self.spawned), 1)
        self.assertEqual(
            self.spawned[0][-4:],
            ["bot_loker_wfh", "fill-form", "--application-id", application_id],
        )
        self.assertIn("Membuka browser", self.client.texts[-1][1])

    def test_fill_button_after_approval_and_unsupported_site(self):
        runner = self.runner(enabled=True)
        application_id = self.approve(runner)
        self.assertEqual(self.client.answers[-1][1], "Application approved.")

        runner.handle_update(callback_update(OWNER, f"fill:{application_id}:APPROVED"))
        self.assertEqual(len(self.spawned), 1)

        self.connection.execute(
            "UPDATE jobs SET source = 'remoteok', apply_url = 'https://remoteok.com/x'"
        )
        self.connection.commit()
        runner.handle_update(callback_update(OWNER, f"fill:{application_id}:APPROVED"))
        self.assertEqual(len(self.spawned), 1)
        self.assertIn("https://remoteok.com/x", self.client.texts[-1][1])


if __name__ == "__main__":
    unittest.main()
