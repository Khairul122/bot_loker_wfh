import sqlite3
import unittest
from datetime import datetime, timezone

from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.eligibility import EligibilityEngine
from bot_loker_wfh.filters import FilterConfig, FilterRepository


class FilterRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)
        self.repository = FilterRepository(self.connection)

    def tearDown(self):
        self.connection.close()

    def test_default_filter_contains_target_stack_keywords(self):
        config = self.repository.get()

        self.assertEqual(
            config.role_keywords,
            (
                "laravel",
                "flutter",
                "nestjs",
                "react",
                "python",
                "backend",
                "full stack",
                "mobile developer",
            ),
        )
        self.assertEqual(config.exclusion_keywords, (
            "unpaid",
            "commission only",
            "equity only",
            "must relocate",
        ))
        self.assertEqual(config.max_posting_age_days, 14)
        self.assertEqual(config.min_relevance_score, 0.65)

    def test_update_persists_all_filter_values(self):
        updated = FilterConfig(
            role_keywords=("django", "data engineer"),
            exclusion_keywords=("internship",),
            min_relevance_score=0.8,
            max_posting_age_days=7,
            no_response_after_days=30,
        )

        self.repository.update(updated)

        self.assertEqual(self.repository.get(), updated)

    def test_update_is_used_by_next_eligibility_evaluation(self):
        self.repository.update(
            FilterConfig(
                role_keywords=("django",),
                exclusion_keywords=(),
                min_relevance_score=0.65,
                max_posting_age_days=14,
                no_response_after_days=21,
            )
        )
        engine = EligibilityEngine(
            self.connection,
            now=datetime(2026, 9, 18, tzinfo=timezone.utc),
        )
        job = {
            "id": "job-filter-config",
            "source": "remoteok",
            "external_id": "filter-config",
            "canonical_fingerprint": "filter-config",
            "title": "Django Developer",
            "company": "Acme",
            "description": "Fully remote Django role worldwide.",
            "posted_at": "2026-09-17T00:00:00+00:00",
            "relevance_score": 0.9,
        }

        result = engine.evaluate(job)

        self.assertEqual(result.status, "CANDIDATE")

    def test_invalid_filter_values_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            self.repository.update(
                FilterConfig(("python",), (), 1.1, 14, 21)
            )

        with self.assertRaisesRegex(ValueError, "At least one role keyword"):
            self.repository.update(
                FilterConfig((), (), 0.65, 14, 21)
            )


if __name__ == "__main__":
    unittest.main()
