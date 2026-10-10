from bot_loker_wfh import database
import unittest

from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.office_server import collect_stats, employee_results, hunt_jobs, hunt_leads


class CollectStatsTest(unittest.TestCase):
    def test_counts_are_grouped_and_contain_no_job_text(self):
        connection = database.connect()
        apply_schema(connection)
        for job_id, source, status in [
            ("a", "remoteok", "CANDIDATE"),
            ("b", "remoteok", "FILTERED_OUT"),
            ("c", "greenhouse", "FILTERED_OUT"),
        ]:
            connection.execute(
                "INSERT INTO jobs (id, source, external_id, source_external_key, "
                "canonical_fingerprint, title, company, description, apply_url, status) "
                "VALUES (?, ?, ?, ?, ?, 'Secret title', 'Co', 'Secret desc', 'https://x', ?)",
                (job_id, source, job_id, f"{source}:{job_id}", f"fp-{job_id}", status),
            )
        connection.execute(
            "INSERT INTO applications (id, job_id, idempotency_key, status, cover_letter, cv_summary) "
            "VALUES ('app', 'a', 'k', 'SUBMITTED', 'Secret letter', 'CV')"
        )

        stats = collect_stats(connection)

        self.assertEqual(stats["jobs"]["remoteok"], {"CANDIDATE": 1, "FILTERED_OUT": 1})
        self.assertEqual(stats["jobs"]["greenhouse"], {"FILTERED_OUT": 1})
        self.assertEqual(stats["applications"], {"SUBMITTED": 1})
        self.assertEqual(stats["history"], 0)
        self.assertNotIn("Secret", repr(stats))

    def test_hunt_returns_inserted_count_and_newest_freelancer_leads(self):
        connection = database.connect()
        apply_schema(connection)

        class FakeLeadService:
            def collect(self):
                connection.execute(
                    "INSERT INTO leads (id, source, external_id, kind, title, description, url, budget) "
                    "VALUES ('l1', 'freelancer', '1', 'project', 'Build Laravel API', 'd', "
                    "'https://www.freelancer.com/projects/x', '$100')"
                )
                connection.execute(
                    "INSERT INTO leads (id, source, external_id, kind, title, description, url) "
                    "VALUES ('l2', 'projects_co_id', '2', 'project', 'Other source', 'd', 'https://p')"
                )
                return {"freelancer": 1}

        result = hunt_leads(connection, FakeLeadService(), "freelancer")

        self.assertEqual(result["inserted"], 1)
        self.assertEqual(
            result["top"],
            [{"title": "Build Laravel API", "sub": "$100",
              "url": "https://www.freelancer.com/projects/x", "kind": "project"}],
        )

    def test_hunt_jobs_scores_then_returns_candidates_of_that_source_only(self):
        connection = database.connect()
        apply_schema(connection)

        def insert(job_id, source):
            connection.execute(
                "INSERT INTO jobs (id, source, external_id, source_external_key, canonical_fingerprint, "
                "title, company, description, location, apply_url) "
                "VALUES (?, ?, ?, ?, ?, 'Laravel Dev', 'Acme', 'd', 'Remote', 'https://apply')",
                (job_id, source, job_id, f"{source}:{job_id}", f"fp-{job_id}"),
            )

        class FakeFetcher:
            def fetch_and_store(self):
                insert("r1", "remoteok")
                insert("g1", "greenhouse")
                return 2

        class FakePipeline:
            def process_discovered(self):
                connection.execute("UPDATE jobs SET status = 'CANDIDATE'")
                return {"candidate": 2, "filtered_out": 0}

        result = hunt_jobs(connection, "remoteok", FakeFetcher(), FakePipeline())

        self.assertEqual((result["inserted"], result["matched"]), (2, 2))
        self.assertEqual(
            result["top"],
            [{"title": "Laravel Dev", "sub": "Acme · Remote", "url": "https://apply", "kind": "job"}],
        )


    def test_employee_results_cover_every_view_and_filter_jobs_by_source(self):
        connection = database.connect()
        apply_schema(connection)
        for job_id, source in [("a", "remoteok"), ("b", "greenhouse")]:
            connection.execute(
                "INSERT INTO jobs (id, source, external_id, source_external_key, canonical_fingerprint, "
                "title, company, description, apply_url, status, filtered_reason) "
                "VALUES (?, ?, ?, ?, ?, 'Dev', 'Co', 'd', 'https://x', 'FILTERED_OUT', 'role mismatch')",
                (job_id, source, job_id, f"{source}:{job_id}", f"fp-{job_id}"),
            )

        jobs = employee_results(connection, "jobs", "remoteok")

        self.assertEqual(len(jobs), 1)
        self.assertEqual((jobs[0]["tag"], jobs[0]["detail"]), ("FILTERED_OUT", "role mismatch"))
        for view in ("screened", "drafts", "applied", "tracking"):
            self.assertIsInstance(employee_results(connection, view), list)
        self.assertEqual(employee_results(connection, "leads", "projects.co.id"), [])
        self.assertEqual(employee_results(connection, "nope"), [])


if __name__ == "__main__":
    unittest.main()
