"""Skill-coverage relevance scoring against the safe CV profile."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable

from .cv_profile import SafeCvProfile
from .relevance_scorer import RelevanceScore


MODEL = "skill-coverage"
VERSION = "1"
# Number of distinct profile skills that must appear in a posting for a full score.
FULL_SCORE_HITS = 3

_ALIASES = {
    "nestjs": ("nest.js", "nest js"),
    "react": ("reactjs", "react.js"),
    "tailwind css": ("tailwind", "tailwindcss"),
}


def matched_skills(text: str, skills: Iterable[str]) -> list[str]:
    haystack = text.lower()
    matches = []
    for skill in skills:
        key = skill.strip().lower()
        if not key:
            continue
        terms = (key, *_ALIASES.get(key, ()))
        if any(_contains_term(haystack, term) for term in terms):
            matches.append(skill)
    return matches


def _contains_term(haystack: str, term: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", haystack) is not None


class SkillCoverageScorer:
    """Scores a job by how many of the candidate's skills the posting mentions."""

    def __init__(self, connection: sqlite3.Connection, profile: SafeCvProfile) -> None:
        self.connection = connection
        self.profile = profile

    def score_job(self, job_id: str) -> RelevanceScore:
        row = self.connection.execute(
            "SELECT title, description FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Job not found: {job_id}")
        hits = matched_skills(f"{row[0]}\n{row[1]}", self.profile.skills)
        score = min(1.0, len(hits) / FULL_SCORE_HITS)
        self.connection.execute(
            "UPDATE jobs SET relevance_score = ?, embedding_model = ?, "
            "embedding_version = ? WHERE id = ?",
            (score, MODEL, VERSION, job_id),
        )
        self.connection.commit()
        return RelevanceScore(job_id, score, MODEL, VERSION)
