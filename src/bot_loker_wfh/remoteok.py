"""RemoteOK fetcher and persistence adapter."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


REMOTEOK_URL = "https://remoteok.com/api"


class RetryableFetchError(RuntimeError):
    """Raised when fetching RemoteOK fails after bounded retries."""


class RemoteOKFetcher:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        fetch_json: Callable[[], list[dict[str, Any]]] | None = None,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self.connection = connection
        self.fetch_json = fetch_json or fetch_remoteok_json
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

    def fetch_and_store(self) -> int:
        payload = self._fetch_with_retries()
        inserted_count = 0
        for item in _job_items(payload):
            if self._insert_job(item):
                inserted_count += 1
        self.connection.commit()
        return inserted_count

    def _fetch_with_retries(self) -> list[dict[str, Any]]:
        for attempt in range(self.max_retries + 1):
            try:
                return self.fetch_json()
            except (OSError, URLError, TimeoutError) as error:
                if attempt >= self.max_retries:
                    raise RetryableFetchError(
                        f"RemoteOK fetch failed after {attempt + 1} attempts"
                    ) from error
                if self.retry_delay_seconds > 0:
                    time.sleep(self.retry_delay_seconds)
        raise AssertionError("unreachable")

    def _insert_job(self, item: dict[str, Any]) -> bool:
        normalized = _normalize_job(item)
        try:
            self.connection.execute(
                "INSERT INTO jobs (id, source, external_id, source_external_key, "
                "canonical_fingerprint, title, company, description, location, "
                "salary_min, salary_max, currency, apply_url, posted_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    "remoteok",
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


def fetch_remoteok_json() -> list[dict[str, Any]]:
    request = Request(
        REMOTEOK_URL,
        headers={"User-Agent": "bot-loker-wfh/0.1"},
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def _job_items(payload: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for item in payload:
        if item.get("id") and item.get("position") and item.get("company"):
            yield item


def _normalize_job(item: dict[str, Any]) -> dict[str, Any]:
    source = "remoteok"
    external_id = str(item["id"])
    title = str(item["position"]).strip()
    company = str(item["company"]).strip()
    apply_url = str(item.get("apply_url") or item.get("url") or "").strip()
    if not apply_url:
        raise ValueError(f"RemoteOK job {external_id} has no apply URL")
    description = str(item.get("description") or "").strip()
    source_external_key = f"{source}:{external_id}"
    canonical_value = "|".join(
        (_normalize_text(title), _normalize_company(company), _normalize_url(apply_url))
    )

    return {
        "external_id": external_id,
        "source_external_key": source_external_key,
        "canonical_fingerprint": hashlib.sha256(
            canonical_value.encode("utf-8")
        ).hexdigest(),
        "title": title,
        "company": company,
        "description": description,
        "location": item.get("location"),
        "salary_min": item.get("salary_min"),
        "salary_max": item.get("salary_max"),
        "currency": item.get("salary_currency") or item.get("currency"),
        "apply_url": apply_url,
        "posted_at": _normalize_timestamp(item.get("date") or item.get("posted_at")),
    }


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().replace("-", " ").split()).replace(
        " senior ", " senior "
    ).strip()


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
