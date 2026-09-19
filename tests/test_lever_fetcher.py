import json
import sqlite3
import unittest
from pathlib import Path
from urllib.error import URLError

from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.lever import LeverFetcher, RetryableFetchError


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "lever_jobs.json"
COMPANIES = [
    ("Acme Inc.", "acme"),
    ("Beta Corp", "betacorp"),
    ("Delta Tech LLC", "deltatech"),
    ("Omega Corp", "omegacorp"),
    ("Sigma Com", "sigmacom"),
]


class LeverFetcherTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)
        for company_name, slug in COMPANIES:
            self.connection.execute(
                "INSERT INTO companies_ats (id, company_name, ats_type, ats_slug, active) "
                "VALUES (?, ?, ?, ?, ?)",
                (f"{slug}-lever", company_name, "lever", slug, 1),
            )
        self.connection.commit()
        self.payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def tearDown(self):
        self.connection.close()

    def test_fetches_normalizes_and_persists_lever_jobs(self):
        fetcher = LeverFetcher(
            self.connection,
            fetch_company_jobs=lambda slug: self.payload.get(slug, []),
        )

        self.assertEqual(fetcher.fetch_and_store(), 6)
        rows = self.connection.execute(
            "SELECT source, external_id, title, company, location, salary_min, "
            "salary_max, currency, apply_url, posted_at, status FROM jobs "
            "ORDER BY external_id"
        ).fetchall()
        first = rows[0]
        self.assertEqual(first[0], "lever")
        self.assertEqual(first[1], "abc-123")
        self.assertEqual(first[2], "Backend Engineer")
        self.assertEqual(first[3], "Acme Inc.")
        self.assertEqual(first[4], "Remote - Worldwide")
        self.assertEqual(first[5:8], (70000, 90000, "USD"))
        self.assertEqual(first[8], "https://jobs.lever.co/acme/abc-123/apply")
        self.assertEqual(first[9], "2026-09-18T09:00:00+00:00")
        self.assertEqual(first[10], "DISCOVERED")

    def test_companies_ats_stores_lever_slug(self):
        rows = self.connection.execute(
            "SELECT company_name, ats_type, ats_slug FROM companies_ats "
            "WHERE ats_type = 'lever' ORDER BY company_name"
        ).fetchall()
        self.assertEqual([row[0] for row in rows], [item[0] for item in COMPANIES])
        self.assertEqual([row[2] for row in rows], [item[1] for item in COMPANIES])

    def test_description_and_lists_are_normalized(self):
        fetcher = LeverFetcher(
            self.connection,
            fetch_company_jobs=lambda slug: self.payload.get(slug, []),
        )
        fetcher.fetch_and_store()
        description = self.connection.execute(
            "SELECT description FROM jobs WHERE external_id = 'abc-123'"
        ).fetchone()[0]
        self.assertIn("Build Python APIs", description)
        self.assertIn("Own backend services", description)
        self.assertNotIn("<p>", description)

    def test_inactive_and_non_lever_companies_are_skipped(self):
        self.connection.execute(
            "INSERT INTO companies_ats (id, company_name, ats_type, ats_slug, active) "
            "VALUES (?, ?, ?, ?, ?)",
            ("inactive", "Inactive", "lever", "inactive", 0),
        )
        self.connection.execute(
            "INSERT INTO companies_ats (id, company_name, ats_type, ats_slug, active) "
            "VALUES (?, ?, ?, ?, ?)",
            ("gh", "Greenhouse Co", "greenhouse", "acme", 1),
        )
        self.connection.commit()
        fetcher = LeverFetcher(
            self.connection,
            fetch_company_jobs=lambda slug: self.payload.get(slug, []),
        )
        self.assertEqual(fetcher.fetch_and_store(), 6)

    def test_second_fetch_is_idempotent(self):
        fetcher = LeverFetcher(
            self.connection,
            fetch_company_jobs=lambda slug: self.payload.get(slug, []),
        )
        self.assertEqual(fetcher.fetch_and_store(), 6)
        self.assertEqual(fetcher.fetch_and_store(), 0)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 6)

    def test_company_failure_does_not_abort_other_companies(self):
        def fetch(slug):
            if slug == "acme":
                raise URLError("temporary outage")
            return self.payload.get(slug, [])

        fetcher = LeverFetcher(self.connection, fetch_company_jobs=fetch)
        self.assertEqual(fetcher.fetch_and_store(), 4)

    def test_retry_exhaustion(self):
        calls = 0

        def fail(slug):
            nonlocal calls
            calls += 1
            raise URLError("outage")

        fetcher = LeverFetcher(
            self.connection,
            fetch_company_jobs=fail,
            max_retries=2,
            retry_delay_seconds=0,
        )
        with self.assertRaises(RetryableFetchError):
            fetcher._fetch_with_retries("acme")
        self.assertEqual(calls, 3)


if __name__ == "__main__":
    unittest.main()

