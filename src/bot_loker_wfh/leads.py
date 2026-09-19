"""Freelance leads: project requests for a fullstack developer and chances to sell source code.

Sources are public JSON endpoints (Freelancer.com's public projects API and the
projects.co.id listing). Leads are stored separately from jobs because they do
not go through the application workflow: the owner just marks them as
interested or ignored and contacts the client through the platform.
"""

from __future__ import annotations

import html
import json
import logging
import re
import sqlite3
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .cv_profile import SafeCvProfile
from .logging_utils import StructuredLogger, sanitize_error
from .telegram_notifications import TelegramButton, TelegramMessage


USER_AGENT = "bot-loker-wfh/0.1 (personal freelance lead search)"
FREELANCER_URL = "https://www.freelancer.com/api/projects/0.1/projects/active/"
PROJECTS_CO_ID_URL = "https://projects.co.id/public/browse_projects/listing"
FREELANCER_QUERIES = (
    "fullstack",
    "laravel",
    "react",
    "flutter",
    "nestjs",
    "website development",
    "source code",
)
MAX_AGE_DAYS = 3
MAX_PROJECTS_PAGES = 10
REQUEST_DELAY_SECONDS = 1.0
JAKARTA = timezone(timedelta(hours=7))

# One STRONG term is enough to mark a lead as relevant to a fullstack developer
# (profile skills count as strong). WEAK terms are too generic on their own, so
# at least two of them are needed.
STRONG_TERMS = (
    "fullstack", "full stack", "laravel", "react", "reactjs", "nestjs", "nest js",
    "flutter", "django", "nodejs", "node js", "php", "web developer",
    "web development", "web app", "aplikasi web", "sistem informasi",
    "pembuatan website", "buat website", "website development", "mobile app",
    "android app", "aplikasi mobile", "aplikasi android",
)
WEAK_TERMS = (
    "developer", "programmer", "backend", "frontend", "api", "source code",
    "sourcecode", "kode sumber",
)
# Phrases that show someone wants to BUY existing code. Plain "source code" is
# not enough: most projects merely require the source code as a deliverable.
SOURCE_CODE_BUYER_TERMS = (
    "buy source code", "buying source code", "purchase source code",
    "source code for sale", "need source code", "looking for source code",
    "want source code", "existing source code", "ready made", "readymade",
    "clone script", "white label", "whitelabel", "script php", "aplikasi jadi",
    "website jadi", "wtb", "beli source", "cari source code", "butuh source code",
    "jual source code", "source code jadi",
)
TITLE_SOURCE_CODE_TERMS = ("source code", "sourcecode", "kode sumber")


@dataclass(frozen=True)
class Lead:
    source: str
    external_id: str
    title: str
    description: str
    url: str
    budget: str | None = None
    posted_at: str | None = None
    kind: str = ""
    score: float = 0.0


def classify(
    title: str, description: str, extra_terms: Sequence[str] = ()
) -> tuple[str | None, float]:
    """Return (kind, score); kind is None when the lead is not relevant."""
    text = f"{title} . {description}".lower().replace("-", " ")
    strong = {term.lower().replace("-", " ") for term in (*STRONG_TERMS, *extra_terms)}
    matched_strong = {term for term in strong if _has_term(text, term)}
    matched_weak = {term for term in WEAK_TERMS if _has_term(text, term)}
    if not matched_strong and len(matched_weak) < 2:
        return None, 0.0
    title_text = title.lower().replace("-", " ")
    is_source_code = any(_has_term(text, term) for term in SOURCE_CODE_BUYER_TERMS) or any(
        _has_term(title_text, term) for term in TITLE_SOURCE_CODE_TERMS
    )
    score = min(1.0, (len(matched_strong) + len(matched_weak) / 2) / 3)
    return ("source_code" if is_source_code else "project"), score


def _has_term(text: str, term: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None


# ------------------------------------------------------------------ sources


class FreelancerFetcher:
    source = "freelancer"

    def __init__(
        self,
        *,
        fetch_json: Callable[[str], dict[str, Any]] | None = None,
        queries: Sequence[str] = FREELANCER_QUERIES,
        delay_seconds: float = REQUEST_DELAY_SECONDS,
    ) -> None:
        self.fetch_json = fetch_json or fetch_freelancer_json
        self.queries = tuple(queries)
        self.delay_seconds = delay_seconds

    def fetch(self) -> list[Lead]:
        leads: dict[str, Lead] = {}
        for index, query in enumerate(self.queries):
            if index and self.delay_seconds > 0:
                time.sleep(self.delay_seconds)
            payload = self.fetch_json(query)
            for project in (payload.get("result") or {}).get("projects") or []:
                lead = _freelancer_lead(project)
                if lead is not None:
                    leads.setdefault(lead.external_id, lead)
        return list(leads.values())


class ProjectsCoIdFetcher:
    source = "projects.co.id"

    def __init__(
        self,
        *,
        fetch_json: Callable[[int], dict[str, Any]] | None = None,
        delay_seconds: float = REQUEST_DELAY_SECONDS,
    ) -> None:
        self.fetch_json = fetch_json or fetch_projects_co_id_json
        self.delay_seconds = delay_seconds

    def fetch(self) -> list[Lead]:
        leads: list[Lead] = []
        page = 1
        while page <= MAX_PROJECTS_PAGES:
            if page > 1 and self.delay_seconds > 0:
                time.sleep(self.delay_seconds)
            payload = self.fetch_json(page)
            for item in payload.get("items") or []:
                lead = _projects_co_id_lead(item)
                if lead is not None:
                    leads.append(lead)
            if page >= int((payload.get("paging") or {}).get("total_pages") or 0):
                break
            page += 1
        return leads


class TelegramChannelFetcher:
    """Reads recent posts of PUBLIC Telegram channels via the t.me/s web preview.

    Only channels the owner lists are read. Private groups are not reachable.
    """

    source = "telegram"
    _CHANNEL = re.compile(r"^[A-Za-z0-9_]{4,32}$")

    def __init__(
        self,
        channels: Sequence[str],
        *,
        fetch_html: Callable[[str], str] | None = None,
        delay_seconds: float = REQUEST_DELAY_SECONDS,
    ) -> None:
        self.channels = tuple(c.strip().lstrip("@") for c in channels if c.strip())
        for channel in self.channels:
            if not self._CHANNEL.match(channel):
                raise ValueError(f"invalid Telegram channel name: {channel!r}")
        self.fetch_html = fetch_html or fetch_telegram_html
        self.delay_seconds = delay_seconds

    def fetch(self) -> list[Lead]:
        leads: list[Lead] = []
        for index, channel in enumerate(self.channels):
            if index and self.delay_seconds > 0:
                time.sleep(self.delay_seconds)
            leads.extend(_telegram_leads(self.fetch_html(channel)))
        return leads


def fetch_telegram_html(channel: str) -> str:
    request = Request(f"https://t.me/s/{channel}", headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


_MESSAGE_SPLIT = re.compile(r'<div class="tgme_widget_message_wrap')
_POST = re.compile(r'data-post="([A-Za-z0-9_]+/\d+)"')
_TEXT = re.compile(
    r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.DOTALL
)
_TIME = re.compile(r'<time[^>]*datetime="([^"]+)"')


def _telegram_leads(page: str) -> list[Lead]:
    leads = []
    for block in _MESSAGE_SPLIT.split(page)[1:]:
        post, text, when = _POST.search(block), _TEXT.search(block), _TIME.search(block)
        if not (post and text and when):
            continue
        body = re.sub(r"<br\s*/?>", " ", text.group(1))
        body = " ".join(html.unescape(re.sub(r"<[^>]+>", "", body)).split())
        if not body:
            continue
        leads.append(
            Lead(
                source="telegram",
                external_id=post.group(1),
                title=body[:80],
                description=body,
                url=f"https://t.me/{post.group(1)}",
                posted_at=when.group(1),
            )
        )
    return leads


def _get_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("unexpected payload")
    return payload


def fetch_freelancer_json(query: str) -> dict[str, Any]:
    params = urlencode(
        {
            "query": query,
            "limit": 30,
            "compact": "true",
            "full_description": "true",
            "sort_field": "time_updated",
        }
    )
    return _get_json(f"{FREELANCER_URL}?{params}")


def fetch_projects_co_id_json(page: int) -> dict[str, Any]:
    return _get_json(f"{PROJECTS_CO_ID_URL}?{urlencode({'page': page})}")


def _freelancer_lead(project: Any) -> Lead | None:
    if not isinstance(project, dict) or not project.get("id") or not project.get("title"):
        return None
    if project.get("deleted") or project.get("nonpublic") or project.get("status") != "active":
        return None
    seo_url = str(project.get("seo_url") or "").strip("/")
    if not seo_url:
        return None
    currency = (project.get("currency") or {}).get("code", "")
    budget = project.get("budget") or {}
    low, high = budget.get("minimum"), budget.get("maximum")
    suffix = "/hour" if project.get("type") == "hourly" else ""
    budget_text = None
    if low is not None or high is not None:
        budget_text = f"{currency} {_money(low)}-{_money(high)}{suffix}".strip()
    bids = (project.get("bid_stats") or {}).get("bid_count")
    if bids is not None:
        budget_text = f"{budget_text or 'Budget n/a'} | {bids} bid"
    submitted = project.get("time_submitted")
    return Lead(
        source="freelancer",
        external_id=str(project["id"]),
        title=str(project["title"]).strip(),
        description=str(project.get("description") or project.get("preview_description") or "").strip(),
        url=f"https://www.freelancer.com/projects/{seo_url}",
        budget=budget_text,
        posted_at=(
            datetime.fromtimestamp(int(submitted), timezone.utc).isoformat()
            if submitted
            else None
        ),
    )


def _projects_co_id_lead(item: Any) -> Lead | None:
    if not isinstance(item, dict) or not item.get("project_id") or not item.get("title"):
        return None
    view = next(
        (
            button.get("url")
            for button in item.get("buttons") or []
            if isinstance(button, dict) and button.get("text") == "View"
        ),
        None,
    )
    if not view:
        return None
    published = item.get("published_date")
    posted_at = None
    if published:
        try:
            posted_at = (
                datetime.strptime(str(published), "%Y-%m-%d %H:%M:%S")
                .replace(tzinfo=JAKARTA)
                .isoformat()
            )
        except ValueError:
            posted_at = None
    bids = item.get("bid_count")
    budget = item.get("budget_range_str") or item.get("published_budget_str")
    if bids is not None:
        budget = f"{budget or 'Budget n/a'} | {bids} bid"
    return Lead(
        source="projects.co.id",
        external_id=str(item["project_id"]),
        title=str(item["title"]).strip(),
        description=" ".join(str(item.get("short_description") or "").split()),
        url=f"https://projects.co.id{view}",
        budget=budget,
        posted_at=posted_at,
    )


def _money(value: Any) -> str:
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return "?"


# ------------------------------------------------------------------ service


class LeadService:
    def __init__(
        self,
        connection: sqlite3.Connection,
        profile: SafeCvProfile,
        *,
        fetchers: Sequence[Any] | None = None,
        max_age_days: int = MAX_AGE_DAYS,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        logger: logging.Logger | None = None,
    ) -> None:
        self.connection = connection
        self.extra_terms = tuple(profile.skills)
        self.fetchers = (
            list(fetchers) if fetchers is not None else [FreelancerFetcher(), ProjectsCoIdFetcher()]
        )
        self.max_age_days = max_age_days
        self.now = now
        self.logger = StructuredLogger(logger or logging.getLogger(__name__))

    def collect(self) -> dict[str, int]:
        """Fetch every source; store new relevant, recent leads. Returns inserted counts."""
        counts: dict[str, int] = {}
        for fetcher in self.fetchers:
            try:
                leads = fetcher.fetch()
            except Exception as error:
                self.logger.error(
                    "lead_fetch_failed",
                    source=fetcher.source,
                    status="error",
                    error_code=sanitize_error(error),
                )
                continue
            counts[fetcher.source] = sum(1 for lead in leads if self._store(lead))
            self.logger.event(
                "lead_fetch_complete",
                source=fetcher.source,
                status="success",
                inserted_count=counts[fetcher.source],
            )
        self.connection.commit()
        return counts

    def _store(self, lead: Lead) -> bool:
        if not self._is_recent(lead.posted_at):
            return False
        kind, score = classify(lead.title, lead.description, self.extra_terms)
        if kind is None:
            return False
        lead = replace(lead, kind=kind, score=score)
        try:
            self.connection.execute(
                "INSERT INTO leads (id, source, external_id, kind, title, description, "
                "url, budget, posted_at, score) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()), lead.source, lead.external_id, lead.kind,
                    lead.title, lead.description, lead.url, lead.budget,
                    lead.posted_at, lead.score,
                ),
            )
        except sqlite3.IntegrityError:
            return False
        return True

    def _is_recent(self, posted_at: str | None) -> bool:
        if not posted_at:
            return False
        try:
            posted = datetime.fromisoformat(posted_at)
        except ValueError:
            return False
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        return self.now() - posted <= timedelta(days=self.max_age_days)

    def unnotified_ids(self, limit: int) -> list[str]:
        rows = self.connection.execute(
            "SELECT id FROM leads WHERE status = 'NEW' AND notified_at IS NULL "
            "ORDER BY score DESC, posted_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [row[0] for row in rows]

    def mark_notified(self, lead_id: str) -> None:
        self.connection.execute(
            "UPDATE leads SET notified_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
            (lead_id,),
        )
        self.connection.commit()

    def set_status(self, lead_id: str, status: str) -> bool:
        if status not in {"INTERESTED", "IGNORED"}:
            raise ValueError("unsupported lead status")
        updated = self.connection.execute(
            "UPDATE leads SET status = ? WHERE id = ?", (status, lead_id)
        ).rowcount
        self.connection.commit()
        return updated == 1

    def message(self, lead_id: str, chat_id: int) -> TelegramMessage | None:
        row = self.connection.execute(
            "SELECT kind, title, source, budget, posted_at, url, description "
            "FROM leads WHERE id = ?",
            (lead_id,),
        ).fetchone()
        if row is None:
            return None
        kind, title, source, budget, posted_at, url, description = row
        label = "Peluang jual source code" if kind == "source_code" else "Proyek dicari developer"
        snippet = " ".join(description.split())[:350]
        text = (
            f"{label}\n{title}\nSumber: {source}\nBudget: {budget or '-'}\n"
            f"Terbit: {(posted_at or '-')[:16]}\n\n{snippet}\n\nLink: {url}"
        )
        return TelegramMessage(
            chat_id=chat_id,
            text=text,
            inline_keyboard=(
                (
                    TelegramButton("Minat", f"lead:{lead_id}:INTERESTED"),
                    TelegramButton("Abaikan", f"lead:{lead_id}:IGNORED"),
                ),
            ),
        )

    def list_text(self, limit: int = 10) -> str:
        rows = self.connection.execute(
            "SELECT kind, title, source, budget, url, status FROM leads "
            "WHERE status IN ('NEW', 'INTERESTED') ORDER BY "
            "CASE status WHEN 'INTERESTED' THEN 0 ELSE 1 END, posted_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        if not rows:
            return "Belum ada lead."
        lines = ["Lead terbaru"]
        for kind, title, source, budget, url, status in rows:
            tag = "SOURCE CODE" if kind == "source_code" else "PROYEK"
            lines.append(f"[{status}] {tag} {title} ({source}, {budget or '-'})\n{url}")
        return "\n\n".join(lines)
