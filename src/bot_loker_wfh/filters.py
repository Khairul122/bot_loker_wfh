"""Persistent eligibility filter configuration."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class FilterConfig:
    role_keywords: tuple[str, ...]
    exclusion_keywords: tuple[str, ...]
    min_relevance_score: float
    max_posting_age_days: int
    no_response_after_days: int
    max_bids: int | None = None


class FilterRepository:
    def __init__(self, connection: sqlite3.Connection, filter_id: str = "default"):
        self.connection = connection
        self.filter_id = filter_id

    def get(self) -> FilterConfig:
        cols = {
            row[1] for row in self.connection.execute("PRAGMA table_info(filters)").fetchall()
        }
        has_bids = "max_bids" in cols
        query = (
            "SELECT role_keywords, exclusion_keywords, min_relevance_score, "
            "max_posting_age_days, no_response_after_days"
            + (", max_bids" if has_bids else "")
            + " FROM filters WHERE id = ?"
        )
        row = self.connection.execute(query, (self.filter_id,)).fetchone()
        if row is None:
            raise ValueError(f"Filter configuration not found: {self.filter_id}")
        max_bids = int(row[5]) if has_bids and row[5] is not None else None
        return FilterConfig(
            role_keywords=tuple(json.loads(row[0])),
            exclusion_keywords=tuple(json.loads(row[1])),
            min_relevance_score=float(row[2]),
            max_posting_age_days=int(row[3]),
            no_response_after_days=int(row[4]),
            max_bids=max_bids,
        )

    def update(self, config: FilterConfig) -> None:
        _validate(config)
        cols = {
            row[1] for row in self.connection.execute("PRAGMA table_info(filters)").fetchall()
        }
        if "max_bids" not in cols:
            self.connection.execute("ALTER TABLE filters ADD COLUMN max_bids INTEGER DEFAULT NULL")
        cursor = self.connection.execute(
            "UPDATE filters SET role_keywords = ?, exclusion_keywords = ?, "
            "min_relevance_score = ?, max_posting_age_days = ?, "
            "no_response_after_days = ?, max_bids = ?, "
            "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
            (
                json.dumps(config.role_keywords),
                json.dumps(config.exclusion_keywords),
                config.min_relevance_score,
                config.max_posting_age_days,
                config.no_response_after_days,
                config.max_bids,
                self.filter_id,
            ),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Filter configuration not found: {self.filter_id}")
        self.connection.commit()


def _validate(config: FilterConfig) -> None:
    if not config.role_keywords:
        raise ValueError("At least one role keyword is required")
    if any(not keyword.strip() for keyword in config.role_keywords):
        raise ValueError("Role keywords cannot be empty")
    if any(not keyword.strip() for keyword in config.exclusion_keywords):
        raise ValueError("Exclusion keywords cannot be empty")
    if not 0 <= config.min_relevance_score <= 1:
        raise ValueError("min_relevance_score must be between 0 and 1")
    if config.max_posting_age_days < 0:
        raise ValueError("max_posting_age_days cannot be negative")
    if config.no_response_after_days < 1:
        raise ValueError("no_response_after_days must be positive")
    if config.max_bids is not None and config.max_bids < 0:
        raise ValueError("max_bids cannot be negative")
