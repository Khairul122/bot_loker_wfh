"""Greenhouse fetcher and persistence adapter."""

from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


GREENHOUSE_API_BASE = "https://boards-api.greenhouse.io/v1/boards"

SOURCE = "greenhouse"


class RetryableFetchError(RuntimeError):
    """Raised when fetching Greenhouse jobs fails after bounded retries."""


class GreenhouseFetcher:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        fetch_company_jobs: Callable[[str], list[dict[str, Any]]] | None = None,
        fetch_job_detail: Callable[[str, int], dict[str, Any]] | None = None,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self.connection = connection
        self.fetch_company_jobs = fetch_company_jobs or _fetch_company_jobs
        self.fetch_job_detail = fetch_job_detail or _fetch_job_detail
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

    def fetch_and_store(self) -> int:
        inserted_count = 0
        company_rows = self._active_greenhouse_companies()
        for company_name, ats_slug in company_rows:
            try:
                jobs = self._fetch_with_retries(ats_slug)
            except Exception:
                continue
            for item in self._normalize_jobs(company_name, ats_slug, jobs):
                if self._insert_job(item):
                    inserted_count += 1
        self.connection.commit()
        return inserted_count

    def _active_greenhouse_companies(self) -> list[tuple[str, str]]:
        rows = self.connection.execute(
            "SELECT company_name, ats_slug FROM companies_ats "
            "WHERE ats_type = ? AND active = 1 ORDER BY company_name",
            (SOURCE,),
        ).fetchall()
        return [(row[0], row[1]) for row in rows]

    def _fetch_with_retries(self, ats_slug: str) -> list[dict[str, Any]]:
        for attempt in range(self.max_retries + 1):
            try:
                return self.fetch_company_jobs(ats_slug)
            except (OSError, URLError, TimeoutError) as error:
                if attempt >= self.max_retries:
                    raise RetryableFetchError(
                        f"Greenhouse fetch for {ats_slug} failed after "
                        f"{attempt + 1} attempts"
                    ) from error
                if self.retry_delay_seconds > 0:
                    time.sleep(self.retry_delay_seconds)
        raise AssertionError("unreachable")

    def _normalize_jobs(
        self, company_name: str, ats_slug: str, payload: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return [
            self._normalize_job(company_name, ats_slug, item)
            for item in payload
            if _is_greenhouse_job(item)
        ]

    def _normalize_job(
        self, company_name: str, ats_slug: str, item: dict[str, Any]
    ) -> dict[str, Any]:
        source = "greenhouse"
        external_id = str(item["id"])
        title = str(item["title"]).strip()
        raw_content = self._load_content(ats_slug, int(external_id))
        text_content = re.sub(r"<[^>]+>", "", raw_content)
        description = html.unescape(text_content).strip()
        if not description:
            description = f"{title} at {company_name}"
        company = str(company_name).strip()
        location = _extract_location(item.get("location"))
        apply_url = str(item.get("absolute_url") or "").strip()
        if not apply_url:
            raise ValueError(f"Greenhouse job {external_id} has no apply URL")
        posted_at = _normalize_timestamp(item.get("first_published"))
        source_external_key = f"{source}:{external_id}"
        canonical_value = "|".join(
            (
                _normalize_text(title),
                _normalize_company(company),
                _normalize_url(apply_url),
            )
        )
        return {
            "source": source,
            "external_id": external_id,
            "source_external_key": source_external_key,
            "canonical_fingerprint": hashlib.sha256(
                canonical_value.encode("utf-8")
            ).hexdigest(),
            "title": title,
            "company": company,
            "description": description,
            "location": location,
            "salary_min": None,
            "salary_max": None,
            "currency": None,
            "apply_url": apply_url,
            "posted_at": posted_at,
        }

    def _load_content(self, ats_slug: str, job_id: int) -> str:
        try:
            detail = self.fetch_job_detail(ats_slug, job_id)
        except Exception:
            return ""
        return str(detail.get("content") or "")

    def _insert_job(self, normalized: dict[str, Any]) -> bool:
        try:
            self.connection.execute(
                "INSERT INTO jobs (id, source, external_id, source_external_key, "
                "canonical_fingerprint, title, company, description, location, "
                "salary_min, salary_max, currency, apply_url, posted_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    normalized["source"],
                    normalized["external_id"],
                    normalized["source_external_key"],
                    normalized["canonical_fingerprint"],
                    normalized["title"],
                    normalized["company"],
                    normalized["description"],
                    normalized["location"],
                    normalized["salary_min"],
                    normalized["salary_max"],
                    normalized["currency"],
                    normalized["apply_url"],
                    normalized["posted_at"],
                ),
            )
        except sqlite3.IntegrityError as error:
            if "UNIQUE constraint failed: jobs." not in str(error):
                raise
            return False
        return True


def _fetch_company_jobs(ats_slug: str) -> list[dict[str, Any]]:
    url = f"{GREENHOUSE_API_BASE}/{ats_slug}/jobs"
    request = Request(
        url,
        headers={"User-Agent": "bot-loker-wfh/0.1"},
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def _fetch_job_detail(ats_slug: str, job_id: int) -> dict[str, Any]:
    url = f"{GREENHOUSE_API_BASE}/{ats_slug}/jobs/{job_id}"
    request = Request(
        url,
        headers={"User-Agent": "bot-loker-wfh/0.1"},
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def _is_greenhouse_job(item: Any) -> bool:
    return isinstance(item, dict) and bool(
        item.get("id") and item.get("title")
    )


def _extract_location(value: Any) -> str | None:
    if isinstance(value, dict):
        return str(value.get("name") or "").strip() or None
    if isinstance(value, str):
        return value.strip() or None
    return None


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().replace("-", " ").split()).strip()


def _normalize_company(value: str) -> str:
    words = _normalize_text(value).replace(",", "").split()
    while words and words[-1] in {"inc", "llc", "ltd", "pt"}:
        words.pop()
    return " ".join(words)


def _normalize_url(value: str) -> str:
    from urllib.parse import urlsplit

    parsed = urlsplit(value)
    if not parsed.netloc:
        return ""
    return f"{parsed.netloc.lower()}{parsed.path.rstrip('/')}"


def _normalize_timestamp(value: Any) -> str | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.isoformat()
