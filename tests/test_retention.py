import sqlite3
import unittest
from datetime import datetime, timezone

from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.retention import FilteredOutRetention


class FilteredOutRetentionTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)
        self.now = datetime(2026, 9, 18, tzinfo=timezone.utc)
        self._insert_job("filtered-old", "FILTERED_OUT", "2026-06-19T00:00:00+00:00")
        self._insert_job("filtered-recent", "FILTERED_OUT", "2026-09-01T00:00:00+00:00")
        self._insert_job("candidate-old", "CANDIDATE", "2026-01-01T00:00:00+00:00")
        self._insert_job("discovered-old", "DISCOVERED", "2026-01-01T00:00:00+00:00")
        self.connection.execute(
            "INSERT INTO applications (id, job_id, idempotency_key, status, cover_letter, cv_summary) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("app-filtered-old", "filtered-old", "key-filtered-old", "DRAFT_READY", "Cover", "CV"),
        )
        self.connection.commit()

    def tearDown(self):
        self.connection.close()

    def _insert_job(self, job_id, status, fetched_at):
        self.connection.execute(
            "INSERT INTO jobs (id, source, external_id, source_external_key, "
            "canonical_fingerprint, title, company, description, apply_url, status, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (job_id, "remoteok", job_id, f"remoteok:{job_id}", f"fp:{job_id}", "Role", "Acme", "desc", "https://example.com/job", status, fetched_at),
        )

    def test_cleanup_deletes_only_old_filtered_jobs_without_applications(self):
        deleted_count = FilteredOutRetention(
            self.connection, now=self.now, retention_days=90
        ).cleanup()

        self.assertEqual(deleted_count, 0)
        self.assertIsNotNone(
            self.connection.execute(
                "SELECT id FROM jobs WHERE id = 'filtered-old'"
            ).fetchone()
        )

    def test_cleanup_deletes_old_filtered_job_after_application_removed(self):
        self.connection.execute("DELETE FROM applications WHERE id = 'app-filtered-old'")
        self.connection.commit()

        deleted_count = FilteredOutRetention(
            self.connection, now=self.now, retention_days=90
        ).cleanup()

        self.assertEqual(deleted_count, 1)
        self.assertIsNone(
            self.connection.execute(
                "SELECT id FROM jobs WHERE id = 'filtered-old'"
            ).fetchone()
        )
        for job_id in ("filtered-recent", "candidate-old", "discovered-old"):
            self.assertIsNotNone(
                self.connection.execute(
                    "SELECT id FROM jobs WHERE id = ?", (job_id,)
                ).fetchone()
            )

    def test_custom_retention_days_can_be_used_for_manual_run(self):
        deleted_count = FilteredOutRetention(
            self.connection, now=self.now, retention_days=7
        ).cleanup()

        self.assertEqual(deleted_count, 1)


if __name__ == "__main__":
    unittest.main()
