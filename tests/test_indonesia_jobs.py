import sqlite3
import unittest

from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.indonesia_jobs import (
    DeallsFetcher,
    KalibrrFetcher,
    RetryableFetchError,
)
from bot_loker_wfh.pipeline import JobPipeline

from test_bot_pipeline import PROFILE

FAST = {"retry_delay_seconds": 0, "page_delay_seconds": 0}


def kalibrr_job(number, *, wfh=True, hybrid=False, name="Backend Engineer"):
    return {
        "id": number,
        "name": f"{name} {number}",
        "slug": f"backend-engineer-{number}",
        "company_name": "PT. Contoh Digital",
        "company": {"code": "contoh-digital", "name": "PT. Contoh Digital"},
        "is_work_from_home": wfh,
        "is_hybrid": hybrid,
        "description": "<p>Membangun API dengan <b>Laravel</b> dan React.</p><ul><li>Python</li></ul>",
        "qualifications": "<p>Pengalaman 2 tahun</p>",
        "base_salary": 8000000,
        "maximum_salary": 12000000,
        "salary_currency": "IDR",
        "activation_date": "2026-09-18T03:15:19.625182+00:00",
        "google_location": {"address_components": {"city": "Central Jakarta", "country": "Indonesia"}},
    }


class KalibrrFetcherTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)
        self.offsets = []

    def fetcher(self, pages):
        def fetch_page(offset):
            self.offsets.append(offset)
            return pages[len(self.offsets) - 1]

        return KalibrrFetcher(self.connection, fetch_page=fetch_page, **FAST)

    def test_stores_only_remote_non_hybrid_jobs_with_normalized_fields(self):
        pages = [
            {"count": 3, "jobs": [kalibrr_job(1), kalibrr_job(2, wfh=False)]},
            {"count": 3, "jobs": [kalibrr_job(3, hybrid=True)]},
        ]

        inserted = self.fetcher(pages).fetch_and_store()

        self.assertEqual(inserted, 1)
        self.assertEqual(self.offsets, [0, 2])
        row = self.connection.execute(
            "SELECT source, external_id, title, company, location, apply_url, "
            "salary_min, salary_max, currency, posted_at, description FROM jobs"
        ).fetchone()
        self.assertEqual(row[:4], ("kalibrr", "1", "Backend Engineer 1", "PT. Contoh Digital"))
        self.assertEqual(row[4], "Remote - Central Jakarta, Indonesia")
        self.assertEqual(row[5], "https://www.kalibrr.com/c/contoh-digital/jobs/1/backend-engineer-1")
        self.assertEqual(row[6:9], (8000000, 12000000, "IDR"))
        self.assertTrue(row[9].startswith("2026-09-18"))
        self.assertIn("Membangun API dengan Laravel dan React.", row[10])
        self.assertNotIn("<", row[10])

    def test_repeat_fetch_is_idempotent(self):
        page = {"count": 1, "jobs": [kalibrr_job(1)]}
        self.assertEqual(self.fetcher([page]).fetch_and_store(), 1)
        self.offsets.clear()
        self.assertEqual(self.fetcher([page]).fetch_and_store(), 0)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 1)

    def test_stops_on_empty_page(self):
        self.assertEqual(self.fetcher([{"count": 99, "jobs": []}]).fetch_and_store(), 0)
        self.assertEqual(self.offsets, [0])

    def test_transient_errors_are_retried_then_raised(self):
        calls = []

        def flaky(offset):
            calls.append(offset)
            if len(calls) < 3:
                raise OSError("boom")
            return {"count": 1, "jobs": [kalibrr_job(1)]}

        self.assertEqual(KalibrrFetcher(self.connection, fetch_page=flaky, **FAST).fetch_and_store(), 1)

        def broken(offset):
            raise TimeoutError

        with self.assertRaises(RetryableFetchError):
            KalibrrFetcher(self.connection, fetch_page=broken, max_retries=1, **FAST).fetch_and_store()

    def test_remote_jobs_flow_through_the_eligibility_pipeline(self):
        self.fetcher([{"count": 1, "jobs": [kalibrr_job(1)]}]).fetch_and_store()
        self.connection.execute("UPDATE jobs SET posted_at = strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')")

        counts = JobPipeline(self.connection, PROFILE).process_discovered()

        self.assertEqual(counts, {"candidate": 1, "filtered_out": 0})


def dealls_doc(number, *, workplace="remote"):
    return {
        "id": f"id{number}",
        "slug": f"fullstack-dev-{number}",
        "role": f"Fullstack Developer {number}",
        "workplaceType": workplace,
        "publishedAt": "2026-09-17T03:33:27.678Z",
        "company": {"name": "Contoh Startup", "slug": "contoh-startup"},
        "skills": [{"name": "React"}, {"name": "NestJS"}],
        "salaryRange": {"start": 10000000, "end": 15000000},
    }


DEALLS_DETAIL = {
    "data": {
        "result": {
            "description": None,
            "responsibilities": "<p>Bangun fitur dengan <strong>Python</strong>.</p>",
            "requirements": "<ul><li>Menguasai Laravel</li></ul>",
        }
    }
}


class DeallsFetcherTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)
        self.detail_calls = []

    def fetcher(self, pages, *, detail=None):
        def fetch_list(page):
            return {"data": pages[page - 1]}

        def fetch_detail(slug):
            self.detail_calls.append(slug)
            return detail(slug) if detail else DEALLS_DETAIL

        return DeallsFetcher(self.connection, fetch_list=fetch_list, fetch_detail=fetch_detail, **FAST)

    def test_stores_remote_jobs_with_detail_text_and_skills(self):
        pages = [
            {"docs": [dealls_doc(1), dealls_doc(2, workplace="onSite")], "totalPages": 2},
            {"docs": [dealls_doc(3)], "totalPages": 2},
        ]

        inserted = self.fetcher(pages).fetch_and_store()

        self.assertEqual(inserted, 2)
        self.assertEqual(self.detail_calls, ["fullstack-dev-1", "fullstack-dev-3"])
        row = self.connection.execute(
            "SELECT title, company, location, apply_url, salary_min, currency, description "
            "FROM jobs WHERE external_id = 'id1'"
        ).fetchone()
        self.assertEqual(row[:3], ("Fullstack Developer 1", "Contoh Startup", "Remote - Indonesia"))
        self.assertEqual(row[3], "https://dealls.com/loker/fullstack-dev-1~contoh-startup")
        self.assertEqual((row[4], row[5]), (10000000, "IDR"))
        for expected in ("Bangun fitur dengan Python.", "Menguasai Laravel", "Skills: React, NestJS"):
            self.assertIn(expected, row[6])

    def test_known_jobs_do_not_trigger_detail_requests(self):
        pages = [{"docs": [dealls_doc(1)], "totalPages": 1}]
        self.fetcher(pages).fetch_and_store()
        self.detail_calls.clear()

        self.assertEqual(self.fetcher(pages).fetch_and_store(), 0)
        self.assertEqual(self.detail_calls, [])

    def test_job_is_retried_next_cycle_when_detail_fails(self):
        pages = [{"docs": [dealls_doc(1)], "totalPages": 1}]

        def failing(slug):
            raise OSError("down")

        self.assertEqual(self.fetcher(pages, detail=failing).fetch_and_store(), 0)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 0)
        self.assertEqual(self.fetcher(pages).fetch_and_store(), 1)


if __name__ == "__main__":
    unittest.main()
