"""Lever Postings API fetcher and persistence adapter."""

from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


LEVER_API_BASE = "https://api.lever.co/v0/postings"
SOURCE = "lever"


class RetryableFetchError(RuntimeError):
    """Raised when fetching Lever jobs fails after bounded retries."""


class LeverFetcher:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        fetch_company_jobs: Callable[[str], list[dict[str, Any]]] | None = None,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self.connection = connection
        self.fetch_company_jobs = fetch_company_jobs or _fetch_company_jobs
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

    def fetch_and_store(self) -> int:
        inserted_count = 0
        for company_name, ats_slug in self._active_lever_companies():
            try:
                jobs = self._fetch_with_retries(ats_slug)
            except Exception:
                continue
            for item in self._normalize_jobs(company_name, item_list=jobs):
                if self._insert_job(item):
                    inserted_count += 1
        self.connection.commit()
        return inserted_count

    def _active_lever_companies(self) -> list[tuple[str, str]]:
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
                        f"Lever fetch for {ats_slug} failed after {attempt + 1} attempts"
                    ) from error
                if self.retry_delay_seconds > 0:
                    time.sleep(self.retry_delay_seconds)
        raise AssertionError("unreachable")

    def _normalize_jobs(
        self, company_name: str, *, item_list: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return [
            _normalize_job(company_name, item)
            for item in item_list
            if _is_lever_job(item)
        ]

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
    url = f"{LEVER_API_BASE}/{ats_slug}?mode=json"
    request = Request(url, headers={"User-Agent": "bot-loker-wfh/0.1"})
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, list):
        raise ValueError("Lever response must be a list of postings")
    return payload


def _is_lever_job(item: Any) -> bool:
    return isinstance(item, dict) and bool(
        item.get("id") and item.get("text") and item.get("applyUrl")
    )


def _normalize_job(company_name: str, item: dict[str, Any]) -> dict[str, Any]:
    external_id = str(item["id"])
    title = str(item["text"]).strip()
    company = str(company_name).strip()
    apply_url = str(item["applyUrl"]).strip()
    if not apply_url:
        raise ValueError(f"Lever job {external_id} has no apply URL")
    description = _normalize_description(item)
    salary_min, salary_max, currency = _normalize_salary(item.get("salaryRange"))
    canonical_value = "|".join(
        (_normalize_text(title), _normalize_company(company), _normalize_url(apply_url))
    )
    return {
        "source": SOURCE,
        "external_id": external_id,
        "source_external_key": f"{SOURCE}:{external_id}",
        "canonical_fingerprint": hashlib.sha256(
            canonical_value.encode("utf-8")
        ).hexdigest(),
        "title": title,
        "company": company,
        "description": description,
        "location": _normalize_location(item.get("categories")),
        "salary_min": salary_min,
        "salary_max": salary_max,
        "currency": currency,
        "apply_url": apply_url,
        "posted_at": _normalize_timestamp(item.get("createdAt")),
    }


def _normalize_description(item: dict[str, Any]) -> str:
    parts: list[str] = []
    plain = str(item.get("descriptionPlain") or "").strip()
    if plain:
        parts.append(plain)
    else:
        description = _html_to_text(item.get("description"))
        if description:
            parts.append(description)
    for section in item.get("lists") or []:
        if not isinstance(section, dict):
            continue
        heading = str(section.get("text") or "").strip()
        content = _html_to_text(section.get("content"))
        if heading and content:
            parts.append(f"{heading}: {content}")
        elif content:
            parts.append(content)
    return "\n\n".join(parts).strip()


def _html_to_text(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return " ".join(html.unescape(text).split()).strip()


def _normalize_location(categories: Any) -> str | None:
    if not isinstance(categories, dict):
        return None
    value = categories.get("location")
    return str(value).strip() or None if value is not None else None


def _normalize_salary(value: Any) -> tuple[int | None, int | None, str | None]:
    if not isinstance(value, dict):
        return None, None, None
    minimum = _integer_or_none(value.get("min"))
    maximum = _integer_or_none(value.get("max"))
    currency = str(value.get("currency") or "").strip() or None
    return minimum, maximum, currency


def _integer_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
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
    if value is None or value == "":
        return None
    try:
        timestamp = float(value) / 1000
    except (TypeError, ValueError, OverflowError):
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
