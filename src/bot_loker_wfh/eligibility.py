"""Deterministic MVP eligibility evaluation for discovered jobs."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .status_transitions import TransitionActor, transition_job_status


@dataclass(frozen=True)
class EligibilityResult:
    status: str
    reason: str | None


class EligibilityEngine:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        now: datetime | None = None,
        filter_id: str = "default",
    ) -> None:
        self.connection = connection
        self.now = _as_utc(now or datetime.now(timezone.utc))
        self.filter_id = filter_id

    def evaluate(self, job: dict[str, Any]) -> EligibilityResult:
        filters = self._load_filters()
        description = str(job.get("description") or "")
        title = str(job.get("title") or "")
        company = str(job.get("company") or "")
        searchable_text = f"{title} {description}".lower().replace("-", " ")

        duplicate_reason = self._duplicate_reason(job)
        if duplicate_reason:
            return EligibilityResult("FILTERED_OUT", duplicate_reason)

        remote_text = f"{description} {job.get('location') or ''}"
        if not _is_fully_remote(remote_text, str(job.get("source") or "")):
            return EligibilityResult("FILTERED_OUT", "not fully remote")

        if _has_region_restriction(description):
            return EligibilityResult("FILTERED_OUT", "region restricted")

        if not _contains_keyword(searchable_text, filters["role_keywords"]):
            return EligibilityResult("FILTERED_OUT", "role mismatch")

        exclusion = _first_keyword(searchable_text, filters["exclusion_keywords"])
        if exclusion:
            return EligibilityResult("FILTERED_OUT", f"excluded keyword: {exclusion}")

        if self._is_blocklisted(company):
            return EligibilityResult("FILTERED_OUT", "company blocked")

        posted_at = _parse_datetime(job.get("posted_at"))
        if posted_at is None:
            return EligibilityResult("FILTERED_OUT", "posting date unavailable")
        if self.now - posted_at > timedelta(days=filters["max_posting_age_days"]):
            return EligibilityResult("FILTERED_OUT", "posting too old")

        relevance_score = job.get("relevance_score")
        if relevance_score is None:
            return EligibilityResult("FILTERED_OUT", "relevance score unavailable")
        if float(relevance_score) < filters["min_relevance_score"]:
            return EligibilityResult(
                "FILTERED_OUT", f"low relevance score: {float(relevance_score):.3f}"
            )

        return EligibilityResult("CANDIDATE", None)

    def evaluate_and_apply(self, job: dict[str, Any]) -> EligibilityResult:
        result = self.evaluate(job)
        if result.status == "FILTERED_OUT":
            transition_job_status(
                self.connection,
                job_id=str(job["id"]),
                to_status="FILTERED_OUT",
                actor=TransitionActor.SYSTEM,
            )
            self.connection.execute(
                "UPDATE jobs SET filtered_reason = ? WHERE id = ?",
                (result.reason, str(job["id"])),
            )
            self.connection.commit()
        else:
            transition_job_status(
                self.connection,
                job_id=str(job["id"]),
                to_status="CANDIDATE",
                actor=TransitionActor.SYSTEM,
            )
        return result

    def _load_filters(self) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT role_keywords, exclusion_keywords, min_relevance_score, "
            "max_posting_age_days FROM filters WHERE id = ?",
            (self.filter_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Filter configuration not found: {self.filter_id}")
        return {
            "role_keywords": [str(item).lower() for item in json.loads(row[0])],
            "exclusion_keywords": [str(item).lower() for item in json.loads(row[1])],
            "min_relevance_score": float(row[2]),
            "max_posting_age_days": int(row[3]),
        }

    def _duplicate_reason(self, job: dict[str, Any]) -> str | None:
        row = self.connection.execute(
            "SELECT id FROM jobs WHERE (source = ? AND external_id = ?) "
            "OR canonical_fingerprint = ? LIMIT 1",
            (
                job.get("source"),
                str(job.get("external_id")),
                job.get("canonical_fingerprint"),
            ),
        ).fetchone()
        if row is not None and str(row[0]) != str(job.get("id")):
            return "duplicate canonical fingerprint"
        return None

    def _is_blocklisted(self, company: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM company_blocklist WHERE lower(company_name) = lower(?) LIMIT 1",
            (company.strip(),),
        ).fetchone()
        return row is not None


# Boards that only list remote jobs; their postings often never say "remote".
REMOTE_ONLY_SOURCES = frozenset({"remoteok", "remotive"})


def _is_fully_remote(description: str, source: str = "") -> bool:
    text = description.lower()
    if any(term in text for term in ("hybrid", "on-site", "onsite", "in-office")):
        return False
    if source in REMOTE_ONLY_SOURCES:
        return True
    return any(term in text for term in ("remote", "worldwide", "anywhere", "fully remote"))


def _has_region_restriction(description: str) -> bool:
    text = " ".join(description.lower().split())
    restricted_phrases = (
        "must be based in",
        "only in the us",
        "us only",
        "eu timezone only",
        "europe timezone only",
        "must have us work authorization",
        "must have u.s. work authorization",
        "must relocate",
    )
    return any(phrase in text for phrase in restricted_phrases)


def _contains_keyword(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _first_keyword(text: str, keywords: list[str]) -> str | None:
    return next((keyword for keyword in keywords if keyword in text), None)


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return _as_utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except ValueError:
        return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

