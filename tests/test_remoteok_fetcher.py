import json
import sqlite3
import unittest
from pathlib import Path
from urllib.error import URLError

from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.remoteok import RemoteOKFetcher, RetryableFetchError


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "remoteok_jobs.json"


class RemoteOKFetcherTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)
        self.payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def tearDown(self):
        self.connection.close()

    def test_fetches_normalizes_and_persists_remoteok_jobs(self):
        fetcher = RemoteOKFetcher(
            self.connection,
            fetch_json=lambda: self.payload,
        )

        inserted_count = fetcher.fetch_and_store()

        job = self.connection.execute(
            "SELECT source, external_id, title, company, description, location, "
            "salary_min, salary_max, currency, apply_url, posted_at, status "
            "FROM jobs"
        ).fetchone()
        self.assertEqual(inserted_count, 1)
        self.assertEqual(
            job,
            (
                "remoteok",
                "remoteok-123",
                "Senior Backend Developer - Remote",
                "Acme Inc.",
                "Build APIs with Python and PostgreSQL.",
                "Worldwide",
                70000,
                90000,
                "USD",
                "https://example.com/jobs/remoteok-123?utm_source=remoteok",
                "2026-09-18T08:00:00+00:00",
                "DISCOVERED",
            ),
        )

    def test_second_fetch_with_same_data_does_not_insert_duplicate(self):
        fetcher = RemoteOKFetcher(
            self.connection,
            fetch_json=lambda: self.payload,
        )

        self.assertEqual(fetcher.fetch_and_store(), 1)
        self.assertEqual(fetcher.fetch_and_store(), 0)
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
            1,
        )

    def test_network_error_is_retried_then_raises(self):
        calls = 0

        def failing_fetch():
            nonlocal calls
            calls += 1
            raise URLError("temporary outage")

        fetcher = RemoteOKFetcher(
            self.connection,
            fetch_json=failing_fetch,
            max_retries=2,
            retry_delay_seconds=0,
        )

        with self.assertRaises(RetryableFetchError):
            fetcher.fetch_and_store()
        self.assertEqual(calls, 3)

    def test_success_after_transient_network_error(self):
        calls = 0

        def flaky_fetch():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError("temporary timeout")
            return self.payload

        fetcher = RemoteOKFetcher(
            self.connection,
            fetch_json=flaky_fetch,
            max_retries=2,
            retry_delay_seconds=0,
        )

        self.assertEqual(fetcher.fetch_and_store(), 1)
        self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()
