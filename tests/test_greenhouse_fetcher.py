import json
import sqlite3
import unittest
from pathlib import Path
from urllib.error import URLError

from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.greenhouse import GreenhouseFetcher, RetryableFetchError


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "greenhouse_jobs.json"


COMPANIES = [
    ("Acme Inc.", "acme"),
    ("Beta Corp", "betacorp"),
    ("Delta Tech LLC", "deltatech"),
    ("Omega Corp", "omegacorp"),
    ("Sigma Com", "sigmacom"),
]

DETAIL_CONTENT = "<p>Build &amp; maintain Python &amp; APIs remotely.</p>"


class GreenhouseFetcherTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)
        self._add_greenhouse_companies(COMPANIES)
        self.payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def tearDown(self):
        self.connection.close()

    def _detail(self, ats_slug, job_id):
        return {"content": DETAIL_CONTENT}

    def test_fetches_normalizes_and_persists_greenhouse_jobs(self):
        fetcher = GreenhouseFetcher(
            self.connection,
            fetch_company_jobs=lambda slug: self.payload.get(slug, []),
            fetch_job_detail=self._detail,
        )

        inserted_count = fetcher.fetch_and_store()

        rows = self.connection.execute(
            "SELECT source, external_id, title, company, location, "
            "apply_url, posted_at, status, salary_min, salary_max, currency "
            "FROM jobs ORDER BY external_id"
        ).fetchall()

        self.assertEqual(inserted_count, 6)
        self.assertEqual(len(rows), 6)
        first = rows[0]
        self.assertEqual(first[0], "greenhouse")
        self.assertEqual(first[1], "1001")
        self.assertEqual(first[2], "Senior Backend Engineer")
        self.assertEqual(first[3], "Acme Inc.")
        self.assertEqual(first[4], "Worldwide")
        self.assertEqual(first[5], "https://www.acme.com/jobs/senior-backend-engineer")
        self.assertEqual(first[6], "2026-09-18T09:00:00+00:00")
        self.assertEqual(first[7], "DISCOVERED")
        self.assertEqual(first[8:], (None, None, None))

    def test_companies_ats_stores_greenhouse_slug(self):
        rows = self.connection.execute(
            "SELECT company_name, ats_type, ats_slug, active "
            "FROM companies_ats WHERE ats_type = 'greenhouse' "
            "ORDER BY company_name"
        ).fetchall()

        self.assertEqual([row[0] for row in rows], [c[0] for c in COMPANIES])
        self.assertEqual([row[2] for row in rows], [c[1] for c in COMPANIES])
        self.assertTrue(all(row[3] == 1 for row in rows))

    def test_inactive_and_non_greenhouse_companies_are_skipped(self):
        self._add_company("Inactive Ltd", "inactive", ats_type="greenhouse", active=0)
        self._add_company("Lever Co", "leverco", ats_type="lever", active=1)

        fetcher = GreenhouseFetcher(
            self.connection,
            fetch_company_jobs=lambda slug: self.payload.get(slug, []),
            fetch_job_detail=self._detail,
        )

        inserted_count = fetcher.fetch_and_store()

        self.assertEqual(inserted_count, 6)

    def test_html_description_is_stripped_and_entities_unescaped(self):
        fetcher = GreenhouseFetcher(
            self.connection,
            fetch_company_jobs=lambda slug: self.payload.get(slug, []),
            fetch_job_detail=self._detail,
        )

        fetcher.fetch_and_store()

        description = self.connection.execute(
            "SELECT description FROM jobs WHERE external_id = '1001'"
        ).fetchone()[0]
        self.assertEqual(
            description, "Build & maintain Python & APIs remotely."
        )

    def test_description_falls_back_to_title_when_detail_unavailable(self):
        fetcher = GreenhouseFetcher(
            self.connection,
            fetch_company_jobs=lambda slug: self.payload.get(slug, []),
            fetch_job_detail=lambda slug, job_id: {"content": None},
        )

        fetcher.fetch_and_store()

        description = self.connection.execute(
            "SELECT description FROM jobs WHERE external_id = '1001'"
        ).fetchone()[0]
        self.assertEqual(description, "Senior Backend Engineer at Acme Inc.")

    def test_second_fetch_with_same_data_does_not_insert_duplicate(self):
        fetcher = GreenhouseFetcher(
            self.connection,
            fetch_company_jobs=lambda slug: self.payload.get(slug, []),
            fetch_job_detail=self._detail,
        )

        self.assertEqual(fetcher.fetch_and_store(), 6)
        self.assertEqual(fetcher.fetch_and_store(), 0)
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
            6,
        )

    def test_company_failure_is_skipped_and_others_still_processed(self):
        def flaky_fetch(slug):
            if slug == "acme":
                raise URLError("temporary outage")
            return self.payload.get(slug, [])

        fetcher = GreenhouseFetcher(
            self.connection,
            fetch_company_jobs=flaky_fetch,
            fetch_job_detail=self._detail,
        )

        inserted_count = fetcher.fetch_and_store()

        self.assertEqual(inserted_count, 4)
        sources = {
            row[0] for row in self.connection.execute("SELECT DISTINCT source FROM jobs")
        }
        self.assertEqual(sources, {"greenhouse"})

    def test_retry_raises_after_max_attempts(self):
        calls = 0

        def always_fail(slug):
            nonlocal calls
            calls += 1
            raise URLError("outage")

        fetcher = GreenhouseFetcher(
            self.connection,
            fetch_company_jobs=always_fail,
            max_retries=2,
            retry_delay_seconds=0,
        )

        with self.assertRaises(RetryableFetchError):
            fetcher._fetch_with_retries("acme")
        self.assertEqual(calls, 3)

    def test_success_after_transient_error(self):
        calls = 0

        def flaky_fetch(slug):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError("temporary timeout")
            return self.payload.get(slug, [])

        fetcher = GreenhouseFetcher(
            self.connection,
            fetch_company_jobs=flaky_fetch,
            fetch_job_detail=self._detail,
            max_retries=2,
            retry_delay_seconds=0,
        )

        self.assertEqual(fetcher.fetch_and_store(), 6)
        self.assertEqual(calls, 6)

    def _add_greenhouse_companies(self, companies):
        for company_name, ats_slug in companies:
            self._add_company(company_name, ats_slug, ats_type="greenhouse", active=1)

    def _add_company(self, company_name, ats_slug, ats_type, active=1):
        self.connection.execute(
            "INSERT INTO companies_ats (id, company_name, ats_type, ats_slug, active) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                company_name + "-" + ats_type,
                company_name,
                ats_type,
                ats_slug,
                active,
            ),
        )
        self.connection.commit()


class GreenhouseBoardEnvelopeTest(unittest.TestCase):
    def test_board_api_envelope_is_unwrapped(self):
        import io
        from unittest.mock import patch

        from bot_loker_wfh import greenhouse

        body = b'{"jobs": [{"id": 1, "title": "Dev"}], "meta": {"total": 1}}'

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch.object(greenhouse, "urlopen", lambda request, timeout: Response(body)):
            self.assertEqual(greenhouse._fetch_company_jobs("acme"), [{"id": 1, "title": "Dev"}])


if __name__ == "__main__":
    unittest.main()
