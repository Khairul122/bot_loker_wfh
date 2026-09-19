"""Score and filter discovered jobs so they become candidates for review."""

from __future__ import annotations

import logging
import sqlite3
from collections import Counter

from .cv_profile import SafeCvProfile
from .eligibility import EligibilityEngine
from .logging_utils import StructuredLogger
from .skill_scorer import SkillCoverageScorer


_JOB_COLUMNS = (
    "id",
    "source",
    "external_id",
    "canonical_fingerprint",
    "title",
    "company",
    "description",
    "posted_at",
    "relevance_score",
)


class JobPipeline:
    def __init__(
        self,
        connection: sqlite3.Connection,
        profile: SafeCvProfile,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self.connection = connection
        self.scorer = SkillCoverageScorer(connection, profile)
        self.engine = EligibilityEngine(connection)
        self.logger = StructuredLogger(logger or logging.getLogger(__name__))

    def process_discovered(self) -> dict[str, int]:
        """Score and evaluate every DISCOVERED job; returns outcome counts."""
        rows = self.connection.execute(
            f"SELECT {', '.join(_JOB_COLUMNS)} FROM jobs "
            "WHERE status = 'DISCOVERED' ORDER BY fetched_at"
        ).fetchall()
        counts: Counter[str] = Counter()
        for row in rows:
            job = dict(zip(_JOB_COLUMNS, row))
            score = self.scorer.score_job(job["id"])
            job["relevance_score"] = score.score
            result = self.engine.evaluate_and_apply(job)
            counts[result.status] += 1
        self.logger.event(
            "eligibility_complete",
            status="success",
            inserted_count=counts["CANDIDATE"],
        )
        return {"candidate": counts["CANDIDATE"], "filtered_out": counts["FILTERED_OUT"]}
