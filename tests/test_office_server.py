import sqlite3
import unittest

from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.office_server import collect_stats, hunt_freelancer


class CollectStatsTest(unittest.TestCase):
    def test_counts_are_grouped_and_contain_no_job_text(self):
        connection = sqlite3.connect(":memory:")
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
        connection = sqlite3.connect(":memory:")
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

        result = hunt_freelancer(connection, FakeLeadService())

        self.assertEqual(result["inserted"], 1)
        self.assertEqual(
            result["top"],
            [{"title": "Build Laravel API", "budget": "$100",
              "url": "https://www.freelancer.com/projects/x", "kind": "project"}],
        )


if __name__ == "__main__":
    unittest.main()
