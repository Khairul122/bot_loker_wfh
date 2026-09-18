"""Remotive fetcher and persistence adapter."""

from __future__ import annotations

import hashlib
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


REMOTIVE_URL = "https://remotive.com/api/remote-jobs"


class RetryableFetchError(RuntimeError):
    """Raised when fetching Remotive fails after bounded retries."""


class RemotiveFetcher:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        fetch_json: Callable[[], dict[str, Any]] | None = None,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self.connection = connection
        self.fetch_json = fetch_json or fetch_remotive_json
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

    def fetch_and_store(self) -> int:
        payload = self._fetch_with_retries()
        inserted_count = 0
        for item in self.normalize_jobs(payload):
            if self._insert_job(item):
                inserted_count += 1
        self.connection.commit()
        return inserted_count

    def normalize_jobs(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        return [_normalize_job(item) for item in payload.get("jobs", []) if _is_job(item)]

    def _fetch_with_retries(self) -> dict[str, Any]:
        for attempt in range(self.max_retries + 1):
            try:
                return self.fetch_json()
            except (OSError, URLError, TimeoutError) as error:
                if attempt >= self.max_retries:
                    raise RetryableFetchError(
                        f"Remotive fetch failed after {attempt + 1} attempts"
                    ) from error
                if self.retry_delay_seconds > 0:
                    time.sleep(self.retry_delay_seconds)
        raise AssertionError("unreachable")

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


def fetch_remotive_json() -> dict[str, Any]:
    request = Request(
        REMOTIVE_URL,
        headers={"User-Agent": "bot-loker-wfh/0.1"},
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def _is_job(item: Any) -> bool:
    return isinstance(item, dict) and bool(
        item.get("id") and item.get("title") and item.get("company_name")
    )


def _normalize_job(item: dict[str, Any]) -> dict[str, Any]:
    source = "remotive"
    external_id = str(item["id"])
    title = str(item["title"]).strip()
    company = str(item["company_name"]).strip()
    apply_url = str(item.get("url") or "").strip()
    if not apply_url:
        raise ValueError(f"Remotive job {external_id} has no apply URL")
    canonical_value = "|".join(
        (_normalize_text(title), _normalize_company(company), _normalize_url(apply_url))
    )
    salary_min, salary_max, currency = _parse_salary(item.get("salary"))
    return {
        "source": source,
        "external_id": external_id,
        "source_external_key": f"{source}:{external_id}",
        "canonical_fingerprint": hashlib.sha256(
            canonical_value.encode("utf-8")
        ).hexdigest(),
        "title": title,
        "company": company,
        "description": str(item.get("description") or "").strip(),
        "location": item.get("candidate_required_location"),
        "salary_min": salary_min,
        "salary_max": salary_max,
        "currency": currency,
        "apply_url": apply_url,
        "posted_at": _normalize_timestamp(item.get("publication_date")),
        "tags": [str(tag).strip().lower() for tag in item.get("tags", []) if tag],
    }


def _parse_salary(value: Any) -> tuple[int | None, int | None, str | None]:
    if not value or str(value).strip().lower() in {"not specified", "n/a"}:
        return None, None, None
    text = str(value)
    numbers = [int(number.replace(",", "")) for number in re.findall(r"\d[\d,]*", text)]
    currency = "USD" if "$" in text or "USD" in text.upper() else None
    if len(numbers) >= 2:
        return numbers[0], numbers[1], currency
    if len(numbers) == 1:
        return numbers[0], numbers[0], currency
    return None, None, currency


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
    return f"{parsed.netloc.lower()}{parsed.path.rstrip('/')}"


def _normalize_timestamp(value: Any) -> str | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.isoformat()
