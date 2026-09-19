"""Embedding-based job relevance scoring."""

from __future__ import annotations

import hashlib
import math
import re
import sqlite3
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any


Embedding = Sequence[float]
Embedder = Callable[[str], Embedding]


@dataclass(frozen=True)
class RelevanceScore:
    job_id: str
    score: float
    model: str
    version: str


class RelevanceScorer:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        embedder: Embedder | None = None,
        model: str = "local-hash-embedding",
        version: str = "1",
    ) -> None:
        if not model.strip() or not version.strip():
            raise ValueError("embedding model and version are required")
        self.connection = connection
        self.embedder = embedder or HashEmbeddingProvider()
        self.model = model
        self.version = version

    def score_job(self, job_id: str, profile_text: str) -> RelevanceScore:
        row = self.connection.execute(
            "SELECT title, description FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Job not found: {job_id}")
        score = _cosine_similarity(
            self.embedder(profile_text), self.embedder(f"{row[0]}\n{row[1]}")
        )
        result = RelevanceScore(job_id, score, self.model, self.version)
        self._persist(result)
        self.connection.commit()
        return result

    def score_jobs(
        self, profile_text: str, job_ids: Iterable[str] | None = None
    ) -> list[RelevanceScore]:
        if job_ids is None:
            rows = self.connection.execute("SELECT id FROM jobs ORDER BY id").fetchall()
            requested_ids = [str(row[0]) for row in rows]
        else:
            requested_ids = [str(job_id) for job_id in job_ids]
        results = []
        for job_id in requested_ids:
            results.append(self.score_job(job_id, profile_text))
        return results

    def _persist(self, result: RelevanceScore) -> None:
        self.connection.execute(
            "UPDATE jobs SET relevance_score = ?, embedding_model = ?, "
            "embedding_version = ? WHERE id = ?",
            (result.score, result.model, result.version, result.job_id),
        )


class HashEmbeddingProvider:
    """Small dependency-free fallback; production providers can be injected."""

    dimensions = 128

    def __call__(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[a-z0-9+#.]+", text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0
        return vector


def _cosine_similarity(left: Embedding, right: Embedding) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions do not match")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    score = sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )
    return max(0.0, min(1.0, score))
