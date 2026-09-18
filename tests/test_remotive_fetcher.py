import json
import sqlite3
import unittest
from pathlib import Path
from urllib.error import URLError

from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.remotive import RemotiveFetcher, RetryableFetchError


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "remotive_jobs.json"


class RemotiveFetcherTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)
        self.payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def tearDown(self):
        self.connection.close()

    def test_fetches_normalizes_and_persists_remotive_jobs(self):
        fetcher = RemotiveFetcher(
            self.connection,
            fetch_json=lambda: self.payload,
        )

        inserted_count = fetcher.fetch_and_store()
        jobs = self.connection.execute(
            "SELECT source, external_id, title, company, location, salary_min, "
            "salary_max, currency, apply_url, posted_at FROM jobs ORDER BY external_id"
        ).fetchall()

        self.assertEqual(inserted_count, 2)
        self.assertEqual(
            jobs,
            [
                (
                    "remotive",
                    "456",
                    "Backend Engineer",
                    "Acme Inc.",
                    "Worldwide",
                    70000,
                    90000,
                    "USD",
                    "https://remotive.com/remote-jobs/software-dev/backend-engineer-456?utm_source=test",
                    "2026-09-18T09:00:00",
                ),
                (
                    "remotive",
                    "457",
                    "Mobile Developer",
                    "Beta LLC",
                    "Anywhere",
                    None,
                    None,
                    None,
                    "https://remotive.com/remote-jobs/mobile/mobile-developer-457",
                    "2026-09-17T09:00:00",
                ),
            ],
        )

    def test_tags_are_normalized_in_fetch_result(self):
        fetcher = RemotiveFetcher(self.connection, fetch_json=lambda: self.payload)

        normalized = fetcher.normalize_jobs(self.payload)[0]

        self.assertEqual(normalized["tags"], ["python", "backend", "postgresql"])
        self.assertEqual(normalized["source"], "remotive")

    def test_second_fetch_with_same_data_does_not_insert_duplicate(self):
        fetcher = RemotiveFetcher(self.connection, fetch_json=lambda: self.payload)

        self.assertEqual(fetcher.fetch_and_store(), 2)
        self.assertEqual(fetcher.fetch_and_store(), 0)
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
            2,
        )

    def test_network_error_is_retried_then_raises(self):
        calls = 0

        def failing_fetch():
            nonlocal calls
            calls += 1
            raise URLError("temporary outage")

        fetcher = RemotiveFetcher(
            self.connection,
            fetch_json=failing_fetch,
            max_retries=2,
            retry_delay_seconds=0,
        )

        with self.assertRaises(RetryableFetchError):
            fetcher.fetch_and_store()
        self.assertEqual(calls, 3)


if __name__ == "__main__":
    unittest.main()
