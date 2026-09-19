import sqlite3
import unittest
from datetime import datetime, timezone

from bot_loker_wfh.database import apply_schema


class DatabaseSchemaTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)

    def tearDown(self):
        self.connection.close()

    def test_creates_required_tables_and_default_filter(self):
        table_names = {
            row[0]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

        self.assertTrue(
            {
                "jobs",
                "applications",
                "submission_attempts",
                "application_status_history",
                "filters",
                "companies_ats",
                "company_blocklist",
            }.issubset(table_names)
        )
        filter_row = self.connection.execute(
            "SELECT role_keywords, exclusion_keywords, min_relevance_score, "
            "max_posting_age_days, no_response_after_days FROM filters"
        ).fetchone()
        self.assertEqual(
            filter_row[0],
            '["laravel", "flutter", "nestjs", "react", "python", "backend", "full stack", "fullstack", "mobile developer", "software engineer", "software developer", "web developer"]',
        )
        self.assertEqual(filter_row[1], '["unpaid", "commission only", "equity only", "must relocate"]')
        self.assertEqual(filter_row[2:], (0.65, 14, 21))

    def test_duplicate_job_keys_and_application_job_are_rejected(self):
        job = (
            "job-1",
            "remoteok",
            "123",
            "remoteok:123",
            "hash-1",
            "Backend Developer",
            "Acme",
            "Description",
            "Worldwide",
            "https://example.com/jobs/123",
            "2026-09-18T00:00:00Z",
        )
        self.connection.execute(
            "INSERT INTO jobs (id, source, external_id, source_external_key, "
            "canonical_fingerprint, title, company, description, location, apply_url, posted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            job,
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "INSERT INTO jobs (id, source, external_id, source_external_key, "
                "canonical_fingerprint, title, company, description, location, apply_url, posted_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (*job[:3], "remoteok:999", "hash-2", *job[5:]),
            )

        application = (
            "application-1",
            "job-1",
            "application-key-1",
            "DRAFT_READY",
            "Cover letter",
            "CV summary",
            "manual",
        )
        self.connection.execute(
            "INSERT INTO applications (id, job_id, idempotency_key, status, "
            "cover_letter, cv_summary, method) VALUES (?, ?, ?, ?, ?, ?, ?)",
            application,
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "INSERT INTO applications (id, job_id, idempotency_key, status, "
                "cover_letter, cv_summary, method) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("application-2", "job-1", "application-key-2", *application[3:]),
            )

    def test_created_at_uses_utc_timestamp(self):
        row = self.connection.execute(
            "SELECT updated_at FROM filters"
        ).fetchone()
        timestamp = datetime.fromisoformat(row[0].replace("Z", "+00:00"))

        self.assertEqual(timestamp.tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main()
