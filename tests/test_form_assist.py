import json
from bot_loker_wfh import database
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
    load_answers,
    load_applicant,
    resolve_form_target,
)
from bot_loker_wfh.pipeline import JobPipeline

from test_bot_pipeline import PROFILE, insert_job
from test_bot_runner import OWNER, FakeClient, callback_update, message_update

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
        self.connection = database.connect()
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


if __name__ == "__main__":
    unittest.main()
