import json
import sqlite3
import unittest
from datetime import datetime, timezone

from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.eligibility import EligibilityEngine, EligibilityResult


NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def job(**overrides):
    value = {
        "id": "job-1",
        "source": "remoteok",
        "external_id": "123",
        "source_external_key": "remoteok:123",
        "canonical_fingerprint": "canonical-123",
        "title": "Backend Developer",
        "company": "Acme",
        "description": "Fully remote backend developer role worldwide.",
        "location": "Worldwide",
        "posted_at": "2026-09-17T12:00:00+00:00",
        "relevance_score": 0.8,
        "status": "DISCOVERED",
    }
    value.update(overrides)
    return value


class EligibilityEngineTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)
        self.engine = EligibilityEngine(self.connection, now=NOW)

    def tearDown(self):
        self.connection.close()

    def test_eligible_job_passes_all_rules(self):
        result = self.engine.evaluate(job())

        self.assertEqual(result, EligibilityResult("CANDIDATE", None))

    def test_rules_are_evaluated_in_order_and_first_failure_wins(self):
        result = self.engine.evaluate(
            job(
                description="Hybrid unpaid role based in US only.",
                relevance_score=0.1,
                posted_at="2020-01-01T00:00:00+00:00",
            )
        )

        self.assertEqual(result.reason, "not fully remote")

    def test_remote_restricted_region_is_filtered(self):
        result = self.engine.evaluate(
            job(description="Fully remote, must be based in US.")
        )

        self.assertEqual(result.reason, "region restricted")

    def test_role_mismatch_is_filtered(self):
        result = self.engine.evaluate(
            job(title="Product Designer", description="Fully remote worldwide design role.")
        )

        self.assertEqual(result.reason, "role mismatch")

    def test_exclusion_keyword_is_filtered(self):
        result = self.engine.evaluate(job(description="Fully remote unpaid backend role worldwide."))

        self.assertEqual(result.reason, "excluded keyword: unpaid")

    def test_blocklisted_company_is_filtered(self):
        self.connection.execute(
            "INSERT INTO company_blocklist (id, company_name, reason) VALUES (?, ?, ?)",
            ("block-1", "Acme", "Do not apply"),
        )
        self.connection.commit()

        result = self.engine.evaluate(job())

        self.assertEqual(result.reason, "company blocked")

    def test_old_posting_is_filtered(self):
        result = self.engine.evaluate(job(posted_at="2026-09-03T11:59:59+00:00"))

        self.assertEqual(result.reason, "posting too old")

    def test_missing_posted_at_is_filtered_with_explicit_reason(self):
        result = self.engine.evaluate(job(posted_at=None))

        self.assertEqual(result.reason, "posting date unavailable")

    def test_low_relevance_is_filtered(self):
        result = self.engine.evaluate(job(relevance_score=0.649))

        self.assertEqual(result.reason, "low relevance score: 0.649")

    def test_missing_relevance_is_filtered_with_explicit_reason(self):
        result = self.engine.evaluate(job(relevance_score=None))

        self.assertEqual(result.reason, "relevance score unavailable")

    def test_duplicate_canonical_fingerprint_is_filtered(self):
        self.connection.execute(
            "INSERT INTO jobs (id, source, external_id, source_external_key, "
            "canonical_fingerprint, title, company, description, apply_url) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("existing", "remotive", "999", "remotive:999", "canonical-123", "Backend Developer", "Other", "x", "https://example.com/other"),
        )
        self.connection.commit()

        result = self.engine.evaluate(job())

        self.assertEqual(result.reason, "duplicate canonical fingerprint")

    def test_apply_updates_status_and_reason_through_transition_service(self):
        self.connection.execute(
            "INSERT INTO jobs (id, source, external_id, source_external_key, "
            "canonical_fingerprint, title, company, description, apply_url) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ? ,?)",
            ("job-1", "remoteok", "123", "remoteok:123", "canonical-123", "Backend Developer", "Acme", "x", "https://example.com/job"),
        )
        self.connection.commit()

        result = self.engine.evaluate_and_apply(job())

        self.assertEqual(result.status, "CANDIDATE")
        self.assertEqual(
            self.connection.execute("SELECT status FROM jobs WHERE id = 'job-1'").fetchone()[0],
            "CANDIDATE",
        )

    def test_apply_persists_filter_reason(self):
        self.connection.execute(
            "INSERT INTO jobs (id, source, external_id, source_external_key, "
            "canonical_fingerprint, title, company, description, apply_url) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("job-filtered", "remoteok", "124", "remoteok:124", "canonical-124", "Backend Developer", "Acme", "Hybrid backend role.", "https://example.com/job"),
        )
        self.connection.commit()

        result = self.engine.evaluate_and_apply(job(id="job-filtered", external_id="124", canonical_fingerprint="canonical-124", description="Hybrid backend role."))

        self.assertEqual(result.reason, "not fully remote")
        self.assertEqual(
            self.connection.execute(
                "SELECT status, filtered_reason FROM jobs WHERE id = 'job-filtered'"
            ).fetchone(),
            ("FILTERED_OUT", "not fully remote"),
        )


class EligibilitySampleCountTest(unittest.TestCase):
    def test_twenty_sample_cases_have_expected_results(self):
        connection = sqlite3.connect(":memory:")
        apply_schema(connection)
        engine = EligibilityEngine(connection, now=NOW)
        samples = [
            job(id=f"job-{index}", external_id=str(index), canonical_fingerprint=f"fp-{index}")
            for index in range(20)
        ]
        samples[1]["description"] = "Hybrid backend developer role."
        samples[2]["description"] = "Fully remote backend role, must be based in US."
        samples[3]["title"] = "Product Designer"
        samples[3]["description"] = "Fully remote design role worldwide."
        samples[4]["description"] = "Fully remote unpaid backend role worldwide."
        samples[5]["posted_at"] = "2026-01-01T00:00:00+00:00"
        samples[6]["relevance_score"] = 0.2
        samples[7]["posted_at"] = None
        samples[8]["relevance_score"] = None

        expected = ["CANDIDATE", "FILTERED_OUT", "FILTERED_OUT", "FILTERED_OUT", "FILTERED_OUT", "FILTERED_OUT", "FILTERED_OUT", "FILTERED_OUT", "FILTERED_OUT"] + ["CANDIDATE"] * 11
        self.assertEqual([engine.evaluate(item).status for item in samples], expected)
        connection.close()


if __name__ == "__main__":
    unittest.main()
