import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from bot_loker_wfh.config import Settings, load_dotenv
from bot_loker_wfh.cv_profile import SafeCvProfile, load_profile
from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.drafts import DraftService, template_cover_letter
from bot_loker_wfh.eligibility import EligibilityEngine
from bot_loker_wfh.pipeline import JobPipeline
from bot_loker_wfh.skill_scorer import SkillCoverageScorer, matched_skills

PROFILE = SafeCvProfile.from_values(
    skills=["Laravel", "Flutter", "NestJS", "React", "Python"],
    experience=["Freelance full-stack developer since 2021."],
    projects=["a NestJS + React client platform"],
)


def recent() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


def insert_job(connection, number, *, title="Backend Engineer", description="",
               source="remoteok", location=None, posted_at=None, status="DISCOVERED"):
    connection.execute(
        "INSERT INTO jobs (id, source, external_id, source_external_key, "
        "canonical_fingerprint, title, company, description, location, apply_url, "
        "posted_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (f"job-{number}", source, str(number), f"{source}:{number}", f"fp-{number}",
         title, "Acme", description, location, f"https://example.com/{number}",
         posted_at or recent(), status),
    )
    connection.commit()


class SkillScorerTest(unittest.TestCase):
    def test_matches_whole_words_and_aliases_only(self):
        self.assertEqual(
            matched_skills("We use Nest.js and React.js daily", PROFILE.skills),
            ["NestJS", "React"],
        )
        self.assertEqual(matched_skills("Reactive programming", PROFILE.skills), [])
        self.assertEqual(matched_skills("PHP and Dart", PROFILE.skills), [])

    def test_score_saturates_at_three_skills_and_is_persisted(self):
        connection = sqlite3.connect(":memory:")
        apply_schema(connection)
        insert_job(connection, 1, description="Python, Laravel and React stack")
        insert_job(connection, 2, description="Only Python here")
        scorer = SkillCoverageScorer(connection, PROFILE)

        self.assertEqual(scorer.score_job("job-1").score, 1.0)
        self.assertAlmostEqual(scorer.score_job("job-2").score, 1 / 3)
        row = connection.execute(
            "SELECT relevance_score, embedding_model FROM jobs WHERE id='job-1'"
        ).fetchone()
        self.assertEqual(row, (1.0, "skill-coverage"))


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)

    def test_relevant_remote_job_becomes_candidate_others_filtered(self):
        insert_job(self.connection, 1, description="Build APIs with Python, NestJS and React.")
        insert_job(self.connection, 2, description="Python only.")
        insert_job(self.connection, 3, title="Sales Rep", description="Sell things.")

        counts = JobPipeline(self.connection, PROFILE).process_discovered()

        self.assertEqual(counts, {"candidate": 1, "filtered_out": 2})
        statuses = dict(self.connection.execute("SELECT id, status FROM jobs").fetchall())
        self.assertEqual(statuses["job-1"], "CANDIDATE")
        self.assertEqual(statuses["job-2"], "FILTERED_OUT")
        self.assertEqual(statuses["job-3"], "FILTERED_OUT")

    def test_already_processed_jobs_are_not_reprocessed(self):
        insert_job(self.connection, 1, description="Python, NestJS, React", status="CANDIDATE")

        self.assertEqual(
            JobPipeline(self.connection, PROFILE).process_discovered(),
            {"candidate": 0, "filtered_out": 0},
        )

    def test_hyphenated_fullstack_title_matches_role_keywords(self):
        insert_job(self.connection, 1, title="Senior Full-Stack Developer",
                   description="Python, Laravel, React.")

        JobPipeline(self.connection, PROFILE).process_discovered()

        self.assertEqual(
            self.connection.execute("SELECT status FROM jobs").fetchone()[0], "CANDIDATE"
        )


class RemoteRuleTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)
        self.engine = EligibilityEngine(self.connection)

    def job(self, **overrides):
        job = {
            "id": "x", "source": "greenhouse", "external_id": "x",
            "canonical_fingerprint": "x", "title": "Python Developer",
            "company": "Acme", "description": "Build things in Python.",
            "posted_at": recent(), "relevance_score": 1.0, "location": None,
        }
        job.update(overrides)
        return job

    def test_ats_job_without_remote_signal_is_rejected(self):
        self.assertEqual(self.engine.evaluate(self.job()).reason, "not fully remote")

    def test_remote_location_field_counts_for_ats_jobs(self):
        self.assertEqual(self.engine.evaluate(self.job(location="Remote - Worldwide")).status, "CANDIDATE")

    def test_remote_only_board_does_not_need_the_word_remote(self):
        self.assertEqual(self.engine.evaluate(self.job(source="remoteok")).status, "CANDIDATE")

    def test_hybrid_is_rejected_even_on_remote_only_board(self):
        job = self.job(source="remoteok", description="Hybrid role, Python.")
        self.assertEqual(self.engine.evaluate(job).reason, "not fully remote")


class DraftServiceTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)
        insert_job(self.connection, 1, description="We use NestJS and React.", status="CANDIDATE")

    def test_template_draft_is_created_pending_and_mentions_matched_stack(self):
        result = DraftService(self.connection, PROFILE).prepare("job-1")

        self.assertEqual(result.status, "created")
        self.assertEqual(result.application_status, "PENDING_APPROVAL")
        letter = self.connection.execute("SELECT cover_letter FROM applications").fetchone()[0]
        self.assertIn("NestJS and React", letter)
        self.assertIn("Acme", letter)
        self.assertEqual(
            self.connection.execute("SELECT method FROM applications").fetchone()[0],
            "template",
        )
        history = self.connection.execute(
            "SELECT from_status, to_status FROM application_status_history"
        ).fetchall()
        self.assertEqual(history, [("DRAFT_READY", "PENDING_APPROVAL")])

    def test_second_prepare_returns_existing_application(self):
        service = DraftService(self.connection, PROFILE)
        first = service.prepare("job-1")
        second = service.prepare("job-1")

        self.assertEqual(second.status, "existing")
        self.assertEqual(second.application_id, first.application_id)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM applications").fetchone()[0], 1)

    def test_llm_output_is_used_when_available(self):
        DraftService(self.connection, PROFILE, llm=lambda prompt: "LLM LETTER").prepare("job-1")

        self.assertEqual(
            self.connection.execute("SELECT cover_letter FROM applications").fetchone()[0],
            "LLM LETTER",
        )
        self.assertEqual(
            self.connection.execute("SELECT method FROM applications").fetchone()[0], "llm"
        )

    def test_llm_failure_falls_back_to_template(self):
        def broken(prompt):
            raise OSError("network down")

        result = DraftService(self.connection, PROFILE, llm=broken).prepare("job-1")

        self.assertEqual(result.application_status, "PENDING_APPROVAL")
        letter = self.connection.execute("SELECT cover_letter FROM applications").fetchone()[0]
        self.assertTrue(letter.startswith("Dear Hiring Team at Acme"))

    def test_non_candidate_and_unknown_jobs_are_refused(self):
        insert_job(self.connection, 2, description="Python", status="FILTERED_OUT")
        service = DraftService(self.connection, PROFILE)

        self.assertEqual(service.prepare("job-2").error_code, "job_not_candidate")
        self.assertEqual(service.prepare("nope").error_code, "job_not_found")

    def test_template_falls_back_to_core_stack_when_nothing_matches(self):
        letter = template_cover_letter(
            title="Designer", company="Acme", description="Draw.", profile=PROFILE
        )
        self.assertIn("My core stack includes Laravel, Flutter, NestJS and React", letter)


class ConfigTest(unittest.TestCase):
    def test_dotenv_is_loaded_but_real_environment_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "﻿# comment\nTELEGRAM_BOT_TOKEN='abc'\nAPP_ENV=production\nEMPTY=\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"APP_ENV": "staging"}, clear=False):
                os.environ.pop("TELEGRAM_BOT_TOKEN", None)
                load_dotenv(path)
                self.assertEqual(os.environ["TELEGRAM_BOT_TOKEN"], "abc")
                self.assertEqual(os.environ["APP_ENV"], "staging")
                os.environ.pop("TELEGRAM_BOT_TOKEN", None)
                os.environ.pop("EMPTY", None)

    def test_new_settings_have_defaults(self):
        settings = Settings.from_environment({})
        self.assertEqual(settings.profile_path, "data/profile.json")
        self.assertIsNone(settings.anthropic_api_key)
        self.assertEqual(settings.fetch_interval_hours, 4.0)

    def test_load_profile_reads_json_and_sanitizes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text(
                '{"skills": ["Python"], "experience": ["Mail me at me@example.com"]}',
                encoding="utf-8",
            )
            profile = load_profile(path)
        self.assertEqual(profile.skills, ("Python",))
        self.assertNotIn("me@example.com", profile.to_summary())
        with self.assertRaises(FileNotFoundError):
            load_profile("does-not-exist.json")


if __name__ == "__main__":
    unittest.main()
