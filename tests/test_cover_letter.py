import logging
import sqlite3
import unittest
from io import StringIO

from bot_loker_wfh.cover_letter import CoverLetterGenerator
from bot_loker_wfh.cv_profile import SafeCvProfile
from bot_loker_wfh.database import apply_schema


class CoverLetterGeneratorTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)
        self.connection.execute(
            "INSERT INTO jobs (id, source, external_id, source_external_key, "
            "canonical_fingerprint, title, company, description, location, apply_url) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "job-1", "lever", "lever-1", "lever:lever-1", "fingerprint-1",
                "Backend Engineer", "Acme",
                "Build Python APIs and own PostgreSQL services for a remote team.",
                "Worldwide", "https://example.com/jobs/1",
            ),
        )
        self.connection.commit()
        self.profile = SafeCvProfile(
            skills=("Python", "PostgreSQL"),
            experience=("Built backend APIs",),
            projects=("Remote reporting platform",),
        )

    def tearDown(self):
        self.connection.close()

    def test_generates_and_persists_llm_draft(self):
        prompts = []

        def provider(prompt):
            prompts.append(prompt)
            return "I am excited to build Python APIs and support PostgreSQL services at Acme."

        result = CoverLetterGenerator(self.connection, provider=provider).generate_and_store(
            job_id="job-1", profile=self.profile
        )

        self.assertEqual(result.status, "created")
        row = self.connection.execute(
            "SELECT job_id, status, cover_letter, cv_summary, method, idempotency_key "
            "FROM applications"
        ).fetchone()
        self.assertEqual(row[:5], (
            "job-1", "DRAFT_READY",
            "I am excited to build Python APIs and support PostgreSQL services at Acme.",
            self.profile.to_summary(), "llm",
        ))
        self.assertTrue(row[5])
        self.assertEqual(len(prompts), 1)
        self.assertIn("Python APIs", prompts[0])
        self.assertIn("PostgreSQL", prompts[0])

    def test_existing_application_is_not_duplicated(self):
        provider_calls = 0

        def provider(prompt):
            nonlocal provider_calls
            provider_calls += 1
            return "A useful draft"

        generator = CoverLetterGenerator(self.connection, provider=provider)
        first = generator.generate_and_store(job_id="job-1", profile=self.profile)
        second = generator.generate_and_store(job_id="job-1", profile=self.profile)

        self.assertEqual(first.status, "created")
        self.assertEqual(second.status, "existing")
        self.assertEqual(provider_calls, 1)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM applications").fetchone()[0], 1)

    def test_provider_failure_returns_failure_without_application(self):
        def provider(prompt):
            raise RuntimeError("provider secret response")

        stream = StringIO()
        logger = logging.getLogger("cover-letter-test")
        logger.handlers.clear()
        logger.propagate = False
        logger.setLevel(logging.INFO)
        logger.addHandler(logging.StreamHandler(stream))

        result = CoverLetterGenerator(
            self.connection, provider=provider, logger=logger
        ).generate_and_store(job_id="job-1", profile=self.profile)

        self.assertEqual(result.status, "failed")
        self.assertIsNone(result.application_id)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM applications").fetchone()[0], 0)
        log_output = stream.getvalue()
        self.assertNotIn("provider secret response", log_output)
        self.assertNotIn("Python APIs", log_output)
        self.assertIn("llm_generation_failed", log_output)

    def test_blank_provider_output_is_rejected(self):
        result = CoverLetterGenerator(
            self.connection, provider=lambda prompt: "   "
        ).generate_and_store(job_id="job-1", profile=self.profile)

        self.assertEqual(result.status, "failed")
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM applications").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()

