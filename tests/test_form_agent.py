"""Unit tests for FormAgent components (extractor, classifier, policy guard, planner, resolver)."""

from __future__ import annotations

import unittest

from bot_loker_wfh.form_agent.answers_v2 import AnswerItem, AnswersStore
from bot_loker_wfh.form_agent.classifier import FieldClassifier
from bot_loker_wfh.form_agent.executor import ValueResolver
from bot_loker_wfh.form_agent.extractor import FormExtractor, FormField
from bot_loker_wfh.form_agent.policy import PlanAction, PolicyGuard
from bot_loker_wfh.form_agent.report import ReportBuilder, SessionRecordInput


class TestFormAgent(unittest.TestCase):
    def test_extractor_parses_snapshot(self):
        snapshot = {
            "children": [
                {"ref": "e1", "role": "textbox", "name": "Email Address", "required": True},
                {"ref": "e2", "role": "button", "name": "Submit Application"},
            ]
        }
        extractor = FormExtractor()
        fields = extractor.extract(snapshot)
        self.assertEqual(len(fields), 2)
        self.assertEqual(fields[0].ref, "e1")
        self.assertEqual(fields[0].label, "Email Address")
        self.assertTrue(fields[0].required)

    def test_classifier_rule_priority(self):
        classifier = FieldClassifier()

        captcha_field = FormField(ref="1", label="Please solve hCaptcha", role="textbox", required=True)
        self.assertEqual(classifier.classify(captcha_field), "captcha")

        upload_field = FormField(ref="2", label="Attach Resume", role="file", required=True)
        self.assertEqual(classifier.classify(upload_field), "upload")

        sensitive_field = FormField(ref="3", label="Gender Identity", role="combobox", required=False)
        self.assertEqual(classifier.classify(sensitive_field), "sensitive")

        identity_field = FormField(ref="4", label="First Name", role="textbox", required=True)
        self.assertEqual(classifier.classify(identity_field), "identity")

    def test_policy_guard_rejects_submit_and_captcha(self):
        guard = PolicyGuard(min_confidence=0.7)

        fields = [
            FormField(ref="e1", label="Solve Captcha", role="textbox", required=True, field_class="captcha"),
            FormField(ref="e2", label="Submit Application", role="button", required=False, field_class="unknown"),
            FormField(ref="e3", label="Email", role="textbox", required=True, field_class="identity"),
        ]

        actions = [
            PlanAction(ref="e1", action="type", value="test", confidence=1.0),
            PlanAction(ref="e2", action="check", value="", confidence=1.0),
            PlanAction(ref="e3", action="type", value="{{applicant.email}}", confidence=1.0),
        ]

        available = ["applicant.email"]
        res = guard.evaluate(actions, fields, available)

        self.assertEqual(len(res.approved), 1)
        self.assertEqual(res.approved[0].ref, "e3")

        rejection_reasons = {r.ref: r.reason for r in res.rejected}
        self.assertEqual(rejection_reasons["e1"], "protected_field")
        self.assertEqual(rejection_reasons["e2"], "forbidden_click")

    def test_value_resolver(self):
        app_data = {"email": "user@example.com", "first_name": "Budi"}
        store = AnswersStore([AnswerItem(key="notice_period", match=("notice",), type="text", value="1 Month")])

        resolver = ValueResolver(applicant_data=app_data, answers_store=store, cover_letter="My draft")

        self.assertEqual(resolver.resolve("{{applicant.email}}"), "user@example.com")
        self.assertEqual(resolver.resolve("{{application.cover_letter}}"), "My draft")
        self.assertEqual(resolver.resolve("{{answers.notice_period}}"), "1 Month")
        self.assertIsNone(resolver.resolve("{{applicant.unknown}}"))

    def test_report_builder_output(self):
        builder = ReportBuilder()
        rec = SessionRecordInput(
            application_id="app-12345678",
            engine="browsermcp",
            host="jobs.lever.co",
            mode="auto_fill",
            page_number=1,
            status="filled",
            company="Acme Corp",
            job_title="Software Engineer",
            all_fields=[],
            executed_events=[],
            rejected_actions=[],
            has_captcha=False,
        )
        text = builder.build_report_text(rec)
        self.assertIn("Form Acme Corp - Software Engineer", text)
        self.assertIn("Form TIDAK dikirim.", text)

    def test_extractor_with_browsermcp_fixtures(self):
        from pathlib import Path
        fixtures_dir = Path("tests/fixtures/browsermcp")
        extractor = FormExtractor()

        for fname in ["greenhouse_job.txt", "lever_job.txt", "ashby_job.txt", "workable_job.txt"]:
            fpath = fixtures_dir / fname
            if fpath.exists():
                text = fpath.read_text(encoding="utf-8")
                fields = extractor.extract(text)
                self.assertGreater(len(fields), 0, f"Failed to extract fields from {fname}")

    def test_candidate_summary_used_in_prompt(self):
        from unittest.mock import MagicMock
        from bot_loker_wfh.form_agent.planner import FormPlanner

        router = MagicMock()
        router.complete.return_value = MagicMock(text="Sample answer")
        planner = FormPlanner(router, None)

        planner.generate_answer(
            "Why do you want to work here?",
            job_summary="Software company",
            candidate_summary="Python developer with 5 years experience",
        )

        call_args = router.complete.call_args[0]
        messages = call_args[1]
        user_msg = messages[1]["content"]

        self.assertIn("Python developer with 5 years experience", user_msg)
        self.assertNotIn("Cover Letter", user_msg)

    def test_ai_answers_off_returns_needs_user_without_calling_router(self):
        from unittest.mock import MagicMock
        from bot_loker_wfh.form_agent.planner import FormPlanner

        router = MagicMock()
        planner = FormPlanner(router, None, ai_answers=False)

        answer = planner.generate_answer("Why do you want to work here?")

        self.assertEqual(answer, "NEEDS_USER")
        router.complete.assert_not_called()


class FreelancerBidSnapshotTest(unittest.TestCase):
    def test_unlabeled_nodes_are_not_fields_and_spinbuttons_are(self):
        from bot_loker_wfh.form_agent.extractor import FormExtractor

        snapshot = (
            "- generic [ref=f1e980]:\n"
            "  - generic [ref=f1e985]:\n"
            '  - spinbutton "Nilai Penawaran" [ref=f1e284]: "500.00"\n'
            '  - spinbutton "Proyek ini akan diselesaikan dalam" [ref=f1e295]: "7"\n'
            '  - textbox "Jelaskan proposal Anda (minimum 100 karakter)" [ref=f1e327]:\n'
            "  - paragraph [ref=f1e330]: some text\n"
        )
        fields = FormExtractor().extract(snapshot)
        self.assertEqual([f.ref for f in fields], ["f1e284", "f1e295", "f1e327"])
        self.assertEqual(fields[0].current_value, "500.00")


class BidProposalClassifierTest(unittest.TestCase):
    def test_bid_proposal_textbox_is_cover_letter(self):
        from bot_loker_wfh.form_agent.classifier import FieldClassifier
        from bot_loker_wfh.form_agent.extractor import FormField

        for label in ("Describe your proposal (minimum 100 characters)", "Jelaskan proposal Anda (minimum 100 karakter)"):
            self.assertEqual(FieldClassifier().classify(FormField("e1", label, "textbox", False)), "cover_letter")
