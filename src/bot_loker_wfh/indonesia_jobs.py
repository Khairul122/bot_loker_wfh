"""Fetchers for Indonesian job boards (Kalibrr, Dealls): remote/WFH postings only.

Both boards expose the JSON their own web apps use, without authentication.
Requests are sequential with a delay between pages and identify the bot in the
User-Agent. Only postings the board itself marks as remote are stored, matching
the project's WFH scope; hybrid and on-site postings are never inserted.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
import time
import uuid
from collections.abc import Callable
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


USER_AGENT = "bot-loker-wfh/0.1 (personal job search)"
KALIBRR_SEARCH_URL = "https://www.kalibrr.com/kjs/job_board/search"
DEALLS_LIST_URL = "https://api.sejutacita.id/v1/explore-job/job"
DEALLS_DETAIL_URL = "https://api.sejutacita.id/v1/job-portal/job/slug/"
PAGE_SIZE = 50
MAX_PAGES = 20
PAGE_DELAY_SECONDS = 1.0


class RetryableFetchError(RuntimeError):
    """Raised when fetching a job board fails after bounded retries."""


class _BoardFetcher:
    source = ""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
        page_delay_seconds: float = PAGE_DELAY_SECONDS,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self.connection = connection
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self.page_delay_seconds = page_delay_seconds

    def _with_retries(self, fetch: Callable[..., Any], *args: Any) -> Any:
        for attempt in range(self.max_retries + 1):
            try:
                return fetch(*args)
            except (OSError, URLError, TimeoutError, ValueError) as error:
                if attempt >= self.max_retries:
                    raise RetryableFetchError(
                        f"{self.source} fetch failed after {attempt + 1} attempts"
                    ) from error
                if self.retry_delay_seconds > 0:
                    time.sleep(self.retry_delay_seconds)
        raise AssertionError("unreachable")

    def _pause(self) -> None:
        if self.page_delay_seconds > 0:
            time.sleep(self.page_delay_seconds)

    def _is_known(self, external_id: str) -> bool:
        return (
            self.connection.execute(
                "SELECT 1 FROM jobs WHERE source_external_key = ?",
                (f"{self.source}:{external_id}",),
            ).fetchone()
            is not None
        )

    def _insert_job(self, normalized: dict[str, Any]) -> bool:
        try:
            self.connection.execute(
                "INSERT INTO jobs (id, source, external_id, source_external_key, "
                "canonical_fingerprint, title, company, description, location, "
                "salary_min, salary_max, currency, apply_url, posted_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    self.source,
                    normalized["external_id"],
                    f"{self.source}:{normalized['external_id']}",
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


class KalibrrFetcher(_BoardFetcher):
    source = "kalibrr"

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        fetch_page: Callable[[int], dict[str, Any]] | None = None,
        **options: Any,
    ) -> None:
        super().__init__(connection, **options)
        self.fetch_page = fetch_page or fetch_kalibrr_page

    def fetch_and_store(self) -> int:
        inserted_count = 0
        offset = 0
        for page_number in range(MAX_PAGES):
            if page_number:
                self._pause()
            page = self._with_retries(self.fetch_page, offset)
            jobs = page.get("jobs") or []
            for item in jobs:
                if _is_kalibrr_remote_job(item) and self._insert_job(
                    _normalize_kalibrr(item)
                ):
                    inserted_count += 1
            offset += len(jobs)
            if not jobs or offset >= int(page.get("count") or 0):
                break
        self.connection.commit()
        return inserted_count


class DeallsFetcher(_BoardFetcher):
    source = "dealls"

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        fetch_list: Callable[[int], dict[str, Any]] | None = None,
        fetch_detail: Callable[[str], dict[str, Any]] | None = None,
        **options: Any,
    ) -> None:
        super().__init__(connection, **options)
        self.fetch_list = fetch_list or fetch_dealls_list
        self.fetch_detail = fetch_detail or fetch_dealls_detail

    def fetch_and_store(self) -> int:
        inserted_count = 0
        page_number = 1
        while page_number <= MAX_PAGES:
            if page_number > 1:
                self._pause()
            data = (self._with_retries(self.fetch_list, page_number) or {}).get("data") or {}
            for doc in data.get("docs") or []:
                if not _is_dealls_remote_job(doc) or self._is_known(str(doc["id"])):
                    continue
                try:
                    self._pause()
                    detail = self._with_retries(self.fetch_detail, str(doc["slug"]))
                except RetryableFetchError:
                    # Without the description the job cannot be scored; because it
                    # is not stored, the next cycle tries again.
                    continue
                if self._insert_job(_normalize_dealls(doc, detail)):
                    inserted_count += 1
            if page_number >= int(data.get("totalPages") or 0):
                break
            page_number += 1
        self.connection.commit()
        return inserted_count


# --------------------------------------------------------------------- HTTP


def _get_json(url: str) -> dict[str, Any]:
    request = Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("unexpected payload")
    return payload


def fetch_kalibrr_page(offset: int) -> dict[str, Any]:
    query = urlencode(
        {
            "limit": PAGE_SIZE,
            "offset": offset,
            "country": "Indonesia",
            "is_work_from_home": "true",
        }
    )
    return _get_json(f"{KALIBRR_SEARCH_URL}?{query}")


def fetch_dealls_list(page: int) -> dict[str, Any]:
    query = urlencode(
        {
            "limit": PAGE_SIZE,
            "page": page,
            "published": "true",
            "sortParam": "publishedAt",
            "sortBy": "desc",
            "workplaceTypes": "remote",
        }
    )
    return _get_json(f"{DEALLS_LIST_URL}?{query}")


def fetch_dealls_detail(slug: str) -> dict[str, Any]:
    return _get_json(f"{DEALLS_DETAIL_URL}{slug}")


# ------------------------------------------------------------ normalization


def _is_kalibrr_remote_job(item: Any) -> bool:
    return (
        isinstance(item, dict)
        and bool(item.get("id") and item.get("name"))
        and bool(item.get("is_work_from_home"))
        and not item.get("is_hybrid")
    )


def _is_dealls_remote_job(doc: Any) -> bool:
    return (
        isinstance(doc, dict)
        and bool(doc.get("id") and doc.get("slug") and doc.get("role"))
        and doc.get("workplaceType") == "remote"
        and isinstance(doc.get("company"), dict)
    )


def _normalize_kalibrr(item: dict[str, Any]) -> dict[str, Any]:
    company_info = item.get("company") if isinstance(item.get("company"), dict) else {}
    company = str(item.get("company_name") or company_info.get("name") or "").strip()
    if not company:
        raise ValueError(f"Kalibrr job {item['id']} has no company")
    title = str(item["name"]).strip()
    code = str(company_info.get("code") or "").strip()
    slug = str(item.get("slug") or "").strip()
    if not (code and slug):
        raise ValueError(f"Kalibrr job {item['id']} has no apply URL")
    apply_url = f"https://www.kalibrr.com/c/{code}/jobs/{item['id']}/{slug}"

    location = _kalibrr_location(item)
    description = _join_text(
        f"{title} at {company}. Remote (work from home) in Indonesia.",
        item.get("description"),
        item.get("qualifications"),
    )
    return {
        "external_id": str(item["id"]),
        "canonical_fingerprint": _fingerprint(title, company, apply_url),
        "title": title,
        "company": company,
        "description": description,
        "location": location,
        "salary_min": _as_int(item.get("base_salary")),
        "salary_max": _as_int(item.get("maximum_salary")),
        "currency": item.get("salary_currency"),
        "apply_url": apply_url,
        "posted_at": _iso(item.get("activation_date")),
    }


def _kalibrr_location(item: dict[str, Any]) -> str:
    location = item.get("google_location")
    parts = []
    if isinstance(location, dict):
        components = location.get("address_components") or {}
        parts = [components.get("city"), components.get("country")]
    place = ", ".join(str(part) for part in parts if part)
    return f"Remote - {place}" if place else "Remote - Indonesia"


def _normalize_dealls(doc: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    result = (detail.get("data") or {}).get("result") or {}
    title = str(doc["role"]).strip()
    company_info = doc["company"]
    company = str(company_info.get("name") or "").strip()
    if not company:
        raise ValueError(f"Dealls job {doc['id']} has no company")
    apply_url = f"https://dealls.com/loker/{doc['slug']}~{company_info.get('slug', '')}"
    skills = ", ".join(
        str(skill.get("name")) for skill in doc.get("skills") or [] if isinstance(skill, dict)
    )
    description = _join_text(
        f"{title} at {company}. Remote (work from home) in Indonesia.",
        result.get("description"),
        result.get("responsibilities"),
        result.get("requirements"),
        f"Skills: {skills}" if skills else None,
    )
    salary = doc.get("salaryRange") if isinstance(doc.get("salaryRange"), dict) else {}
    return {
        "external_id": str(doc["id"]),
        "canonical_fingerprint": _fingerprint(title, company, apply_url),
        "title": title,
        "company": company,
        "description": description,
        "location": "Remote - Indonesia",
        "salary_min": _as_int(salary.get("start")),
        "salary_max": _as_int(salary.get("end")),
        "currency": "IDR" if salary else None,
        "apply_url": apply_url,
        "posted_at": _iso(doc.get("publishedAt")),
    }


def _join_text(*parts: Any) -> str:
    chunks = [_html_to_text(part) for part in parts if part]
    return "\n\n".join(chunk for chunk in chunks if chunk)


def _html_to_text(value: Any) -> str:
    text = re.sub(r"<(br|/p|/li|/ul|/ol|/h\d)[^>]*>", "\n", str(value), flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    lines = (" ".join(line.split()) for line in html.unescape(text).splitlines())
    return "\n".join(line for line in lines if line)


def _fingerprint(title: str, company: str, apply_url: str) -> str:
    value = "|".join((_normalize_text(title), _normalize_company(company), apply_url))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().replace("-", " ").split())


def _normalize_company(value: str) -> str:
    words = _normalize_text(value).replace(",", "").replace(".", "").split()
    while words and words[-1] in {"inc", "llc", "ltd", "pt", "tbk"}:
        words.pop()
    while words and words[0] in {"pt", "cv"}:
        words.pop(0)
    return " ".join(words)


def _as_int(value: Any) -> int | None:
    try:
        return int(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _iso(value: Any) -> str | None:
    return str(value) if value else None
