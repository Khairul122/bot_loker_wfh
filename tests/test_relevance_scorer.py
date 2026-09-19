import sqlite3
import unittest

from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.relevance_scorer import RelevanceScorer


class RelevanceScorerTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)
        for number in range(20):
            self.connection.execute(
                "INSERT INTO jobs (id, source, external_id, source_external_key, "
                "canonical_fingerprint, title, company, description, apply_url) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"job-{number}", "test", str(number), f"test:{number}",
                    f"fingerprint-{number}",
                    f"Python Backend Engineer {number}" if number % 2 == 0 else f"Marketing Writer {number}",
                    "Company",
                    "Build Python APIs and PostgreSQL services." if number % 2 == 0 else "Write brand newsletters and campaign copy.",
                    f"https://example.com/{number}",
                ),
            )
        self.connection.commit()

    def tearDown(self):
        self.connection.close()

    def test_scores_and_persists_model_metadata(self):
        scorer = RelevanceScorer(self.connection)
        result = scorer.score_job("job-0", "Python backend APIs PostgreSQL")

        self.assertGreaterEqual(result.score, 0)
        self.assertLessEqual(result.score, 1)
        row = self.connection.execute(
            "SELECT relevance_score, embedding_model, embedding_version "
            "FROM jobs WHERE id = 'job-0'"
        ).fetchone()
        self.assertEqual(row, (result.score, "local-hash-embedding", "1"))

    def test_relevant_jobs_rank_above_irrelevant_jobs_for_ten_pairs(self):
        scorer = RelevanceScorer(self.connection)
        results = scorer.score_jobs("Python backend APIs PostgreSQL")
        scores = {result.job_id: result.score for result in results}

        for pair in range(10):
            self.assertGreater(scores[f"job-{pair * 2}"], scores[f"job-{pair * 2 + 1}"])

    def test_injected_embedder_is_used_and_dimensions_are_validated(self):
        vectors = {
            "profile": [1.0, 0.0],
            "Backend Engineer\nRelevant": [1.0, 0.0],
        }
        scorer = RelevanceScorer(
            self.connection,
            embedder=lambda text: vectors.get(text, [0.0, 1.0]),
            model="test-model",
            version="test-version",
        )
        result = scorer.score_job("job-0", "profile")
        self.assertEqual(result.model, "test-model")
        self.assertEqual(result.version, "test-version")

    def test_threshold_is_read_from_filter_configuration(self):
        self.connection.execute(
            "UPDATE filters SET min_relevance_score = 0.99 WHERE id = 'default'"
        )
        self.connection.commit()
        row = self.connection.execute(
            "SELECT min_relevance_score FROM filters WHERE id = 'default'"
        ).fetchone()
        self.assertEqual(row[0], 0.99)


if __name__ == "__main__":
    unittest.main()

