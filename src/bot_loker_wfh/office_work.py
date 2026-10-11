"""Owner workflow behind the 3D office: the auto-work cycle and the approval inbox.

Nothing is ever sent without the owner: the cycle only searches, scores and drafts.
Applying starts after an explicit approval, and the form filler stops before submit.
"""

from __future__ import annotations

import logging
from . import database
from .database import Connection
import subprocess
import threading
from datetime import datetime, timezone
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from .auto_bid import run_auto_bids
from .freelancer_api import FreelancerError
from .form_assist import FormAssistError, resolve_form_target, spawn_fill_form, spawn_fill_lead
from .lead_desk import (
    approve_lead, edit_bid_terms, get_bid_terms, lead_counts, list_leads, save_proposal, set_lead_status, undrafted_leads,
)
from .logging_utils import StructuredLogger, sanitize_error
from . import office_desk as desk
from .office_events import bus as office_events
from .status_transitions import (
    InvalidTransitionError,
    TransitionActor,
    mark_applied_manually,
    transition_application_status,
)

DRAFTS_PER_CYCLE = 3
PROPOSALS_PER_CYCLE = 5
MIN_INTERVAL_SECONDS = 5 * 60  # hard floor regardless of configured interval
DAILY_CHECK_SECONDS = 10 * 60
GITHUB_CHECK_SECONDS = 15 * 60  # how often the saved username is checked
GITHUB_SYNC_SECONDS = 6 * 3600  # portfolio older than this is re-synced automatically
# owner's "update status" buttons on sent applications -> the real status transition
STATUS_ACTIONS = {
    "viewed": "VIEWED", "interview": "INTERVIEW", "offer": "OFFER",
    "rejected": "REJECTED_BY_COMPANY", "noresponse": "NO_RESPONSE",
}


@contextmanager
def open_db() -> Iterator[Connection]:
    """Commit on success and always close."""
    connection = database.open_db()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


class OfficeWork:
    def __init__(
        self,
        *,
        hunters: dict[str, Callable[[Connection], dict]],
        draft_service_for: Callable[[Connection], Any],
        form_assist_enabled: bool,
        interval_seconds: float | Callable[[], float],
        lock: threading.Lock,
        freelancer_bid: Callable[[Connection, str], Any] | None = None,
        freelancer_reconcile: Callable[[Connection], int] | None = None,
        proposal_writer: Callable[..., str] | None = None,
        screener: Callable[[Connection], dict] | None = None,
        llm: Callable[[str], str] | None = None,
        notify: Callable[[str], None] | None = None,
        spawn: Callable[..., Any] = subprocess.Popen,
        clock: Callable[[], float] = time.time,
        logger: logging.Logger | None = None,
    ) -> None:
        self.hunters = hunters
        self.draft_service_for = draft_service_for
        self.form_assist_enabled = form_assist_enabled
        self._interval_seconds = interval_seconds
        self.lock = lock  # shared with manual hunts: one search/draft at a time
        self.proposal_writer = proposal_writer
        self.freelancer_bid = freelancer_bid
        self.freelancer_reconcile = freelancer_reconcile
        self.screener = screener  # Sari & Eli: score the DISCOVERED queue now
        self.llm = llm  # answers the owner's questions; None = plain facts
        self.notify = notify  # sends text to the owner's Telegram; None = not configured
        self._lead_fill: Any = None  # the running fill-lead process, if any
        self.spawn = spawn
        self.clock = clock
        self.logger = StructuredLogger(logger or logging.getLogger(__name__))
        self.auto = False
        self.busy: str | None = None
        self.last: dict | None = None
        self.next_at: float | None = None
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ activity log

    def log_work(self, employee: str | None, task: str, *, status: str = "success", **fields: Any) -> None:
        """One JSON line per employee action; counts and names only, never letters or CVs."""
        payload = {
            "type": "employee_work", "task": task, "status": status,
            "employee": employee or "-",
            **{key: value for key, value in fields.items() if value is not None},
        }
        self.logger.event("employee_work", **{key: value for key, value in payload.items() if key != "type"})
        office_events.publish(payload)

    def log_failure(self, employee: str | None, task: str, error: BaseException, **fields: Any) -> None:
        """A failed action still reaches the terminal, with a sanitized error code."""
        payload = {
            "type": "employee_work", "task": task, "status": "error",
            "employee": employee or "-", "error_code": sanitize_error(error),
            **{key: value for key, value in fields.items() if value is not None},
        }
        self.logger.error("employee_work", **{key: value for key, value in payload.items() if key != "type"})
        office_events.publish(payload)

    def _watch(self, process: Any, employee: str, task: str, **fields: Any) -> None:
        """Follow a spawned fill process so its exit lands in the terminal log too."""
        if process is None or not hasattr(process, "wait"):
            return
        if getattr(process, "returncode", None) is not None:
            return  # finished instantly (tests' fake spawn): nothing to watch

        def follow() -> None:
            started = self.clock()
            try:
                code = process.wait()
            except Exception as error:  # the launcher died before the child answered
                self.log_failure(employee, task, error, **fields)
                return
            duration = int((self.clock() - started) * 1000)
            if code == 0:
                self.log_work(employee, task, duration_ms=duration, **fields)
            else:
                self.log_work(employee, task, status="error", duration_ms=duration, **fields)

        threading.Thread(target=follow, name=f"watch-{task}", daemon=True).start()

    # ------------------------------------------------------------------ inbox

    def inbox(self, connection: Connection) -> dict:
        rows = connection.execute(
            "SELECT a.id, a.status, j.title, j.company, j.location, j.apply_url, "
            "j.relevance_score, a.cover_letter FROM applications a JOIN jobs j ON j.id = a.job_id "
            "WHERE a.status IN ('PENDING_APPROVAL', 'APPROVED', 'SUBMITTED', 'VIEWED', 'INTERVIEW') "
            "ORDER BY j.relevance_score DESC, a.created_at DESC"
        ).fetchall()
        items = [
            dict(zip(("id", "status", "title", "company", "location", "url", "score", "letter"), row))
            for row in rows
        ]
        return {
            "pending": [i for i in items if i["status"] == "PENDING_APPROVAL"],
            "approved": [i for i in items if i["status"] == "APPROVED"],
            # Tara's desk: the owner records what the company answered
            "sent": [{**i, "letter": None} for i in items if i["status"] in ("SUBMITTED", "VIEWED", "INTERVIEW")],
            "waiting": self._undrafted_count(connection),
            "form_assist": self.form_assist_enabled,
        }

    def draft_next(self, connection: Connection, limit: int = DRAFTS_PER_CYCLE) -> int:
        """Let Cora draft letters for the best candidates that have none yet.

        Jobs matching Sari's standing instruction (owner keywords) go first.
        """
        rows = connection.execute(
            "SELECT j.id, j.title || ' ' || COALESCE(j.description, '') FROM jobs j "
            "LEFT JOIN applications a ON a.job_id = j.id WHERE j.status = 'CANDIDATE' AND a.id IS NULL "
            "ORDER BY j.relevance_score DESC, j.fetched_at DESC LIMIT 200"
        ).fetchall()
        words = desk.keywords(desk.get_instruction(connection, "sari"))
        rows.sort(key=lambda r: -desk.keyword_hits(r[1], words))  # stable: score order otherwise
        job_ids = [r[0] for r in rows[:limit]]
        service = self.draft_service_for(connection)
        drafted = sum(
            1 for job_id in job_ids if service.prepare(job_id).application_status == "PENDING_APPROVAL"
        )
        # Cora writes the letters; one line whether the cycle or the owner's button asked
        self.log_work("cora", "draft", count=drafted)
        return drafted

    def decide(self, connection: Connection, application_id: str, action: str) -> dict:
        """approve | reject | apply | applied. Raises InvalidTransitionError when stale."""
        started = self.clock()
        try:
            if action in ("approve", "reject"):
                transition_application_status(
                    connection,
                    application_id=application_id,
                    to_status="APPROVED" if action == "approve" else "REJECTED_BY_USER",
                    actor=TransitionActor.USER,
                )
                if action == "reject":
                    result = {"status": "REJECTED_BY_USER"}
                else:
                    result = {"status": "APPROVED", **self._apply(connection, application_id)}
            elif action == "apply":
                if self._status(connection, application_id) != "APPROVED":
                    raise InvalidTransitionError("approve first")
                result = {"status": "APPROVED", **self._apply(connection, application_id)}
            elif action == "applied":
                mark_applied_manually(connection, application_id, via="3D office")
                result = {"status": "SUBMITTED"}
            elif action in STATUS_ACTIONS:
                transition_application_status(
                    connection, application_id=application_id,
                    to_status=STATUS_ACTIONS[action], actor=TransitionActor.USER,
                )
                connection.execute(
                    "UPDATE applications SET last_status_check_at = utc_now_iso() WHERE id = ?",
                    (application_id,),
                )
                result = {"status": STATUS_ACTIONS[action]}
            else:
                raise InvalidTransitionError(f"unknown action: {action}")
        except InvalidTransitionError as error:
            self.log_failure("tegar", "decision", error, application_id=application_id, action=action)
            raise
        # Tegar keeps the approval queue: every owner decision is one line in the terminal
        self.log_work(
            "tegar", "decision", action=action, application_id=application_id,
            status=result.get("status"), mode=result.get("mode"),
            duration_ms=int((self.clock() - started) * 1000),
        )
        return result

    def _apply(self, connection: Connection, application_id: str) -> dict:
        url = connection.execute(
            "SELECT j.apply_url FROM applications a JOIN jobs j ON j.id = a.job_id WHERE a.id = ?",
            (application_id,),
        ).fetchone()[0]
        if self.form_assist_enabled:
            try:
                resolve_form_target(connection, application_id)
                self._watch(
                    spawn_fill_form(application_id, spawn=self.spawn),
                    "faris", "fill", application_id=application_id,
                )
                return {"mode": "form", "url": url}
            except (FormAssistError, OSError) as error:
                # unsupported form or launcher failed: the owner applies by hand
                self.log_failure("faris", "fill", error, application_id=application_id)
        return {"mode": "manual", "url": url}

    @staticmethod
    def _status(connection: Connection, application_id: str) -> str | None:
        row = connection.execute(
            "SELECT status FROM applications WHERE id = ?", (application_id,)
        ).fetchone()
        return row[0] if row else None

    @staticmethod
    def _undrafted_count(connection: Connection) -> int:
        return connection.execute(
            "SELECT COUNT(*) FROM jobs j LEFT JOIN applications a ON a.job_id = j.id "
            "WHERE j.status = 'CANDIDATE' AND a.id IS NULL"
        ).fetchone()[0]

    # ------------------------------------------------------------------ freelance desk

    def draft_proposals(self, connection: Connection, limit: int = PROPOSALS_PER_CYCLE) -> int:
        """Cora pre-writes bids for the best new projects; they stay NEW until the owner acts."""
        lead_ids = undrafted_leads(connection, limit)
        for lead_id in lead_ids:
            self.proposal_writer(connection, lead_id, mark_interested=False)
        self.log_work("cora", "proposal", count=len(lead_ids))
        return len(lead_ids)

    def leads(self, connection: Connection, source: str | None, view: str = "all") -> dict:
        return {"items": list_leads(connection, source, view), "counts": lead_counts(connection, source),
                "browser_fill": self.form_assist_enabled,
                # sources whose approved bid needs the BrowserMCP tab; the others use the API or the bot's own window
                "tab_sources": [s for s in ("freelancer", "projects.co.id", "telegram", "peopleperhour")
                                if not (s == "projects.co.id" or (s == "freelancer" and self.freelancer_bid is not None))]}

    def lead_action(self, connection: Connection, lead_id: str, action: str, body: dict) -> dict:
        """interested | ignored | new | proposal | revise | fill | approve. Raises KeyError for unknown leads."""
        started = self.clock()
        employee, result = self._lead_action(connection, lead_id, action, body)
        self.log_work(
            employee, "lead", action=action, lead_id=lead_id, mode=result.get("mode"),
            duration_ms=int((self.clock() - started) * 1000),
        )
        return result

    def _lead_action(self, connection: Connection, lead_id: str, action: str, body: dict) -> tuple[str, dict]:
        if action in ("interested", "ignored", "new"):
            set_lead_status(connection, lead_id, action.upper())
            return "bimo", {"status": action.upper()}  # the bidding desk files the owner's verdict
        if action == "proposal":
            text = str(body.get("text") or "").strip()
            if text:
                save_proposal(connection, lead_id, text)
            else:
                text = self.proposal_writer(connection, lead_id)
            return "cora", {"proposal": text, "bid_terms": _terms(get_bid_terms(connection, lead_id))}
        if action == "revise":
            note = str(body.get("note") or "").strip()
            if not note:
                raise ValueError("tulis catatan revisinya dulu")
            text = self.proposal_writer(connection, lead_id, mark_interested=True, note=note)
            return "cora", {"proposal": text, "bid_terms": _terms(get_bid_terms(connection, lead_id)), "revised": True}
        if action == "terms":
            terms = edit_bid_terms(connection, lead_id, body)
            return "cora", {"bid_terms": _terms(terms)}
        if action == "fill":
            row = connection.execute("SELECT url, proposal FROM leads WHERE id = ?", (lead_id,)).fetchone()
            if row is None:
                raise KeyError(lead_id)
            if not self.form_assist_enabled or not (row[1] or "").strip():
                return "faris", {"mode": "manual", "url": row[0]}
            if self._filler_busy():
                return "faris", {"mode": "busy", "url": row[0]}
            self._lead_fill = spawn_fill_lead(lead_id, spawn=self.spawn)
            self._watch(self._lead_fill, "faris", "fill", lead_id=lead_id)
            return "faris", {"mode": "form", "url": row[0]}
        if action == "approve":
            # the owner approved proposal + bid terms: the bid goes out for them
            row = connection.execute("SELECT url, source FROM leads WHERE id = ?", (lead_id,)).fetchone()
            if row is None:
                raise KeyError(lead_id)
            if row[1] == "freelancer" and self.freelancer_bid is not None:
                approve_lead(connection, lead_id)  # validates; ValueError carries a user-safe reason
                try:
                    self.freelancer_bid(connection, lead_id)  # official API: no browser, no tab
                except Exception as error:
                    connection.execute("UPDATE leads SET status = 'INTERESTED' WHERE id = ? AND status = 'APPROVED'", (lead_id,))
                    connection.commit()
                    if isinstance(error, FreelancerError):
                        raise ValueError(str(error)) from None
                    raise ValueError("bid gagal dikirim ke Freelancer; coba lagi") from None
                return "faris", {"mode": "api", "status": "SUBMITTED", "url": row[0]}
            if not self.form_assist_enabled:
                return "faris", {"mode": "manual", "url": row[0]}
            if self._filler_busy():
                return "faris", {"mode": "busy", "url": row[0]}
            approve_lead(connection, lead_id)  # validates; ValueError carries a user-safe reason
            self._lead_fill = spawn_fill_lead(lead_id, submit=True, spawn=self.spawn)
            self._watch(self._lead_fill, "faris", "submit", lead_id=lead_id)
            return "faris", {"mode": "submitting", "status": "APPROVED", "url": row[0]}
        raise ValueError(f"unknown action: {action}")

    def _filler_busy(self) -> bool:
        return self._lead_fill is not None and getattr(self._lead_fill, "poll", lambda: 0)() is None

    # ------------------------------------------------------------------ owner's office

    def request_reports(self, connection: Connection, employee: str) -> dict:
        """An employee (or 'all') writes a 24h report now; it is walked to the owner in 3D."""
        names = desk.EMPLOYEES if employee == "all" else (employee,)
        if any(name not in desk.ROLES for name in names):
            raise KeyError(employee)
        reports = [desk.create_report(connection, name) for name in names]
        for report in reports:
            self.log_work(report["employee"], "report", count=len(reports), rating=report["rating"])
        self._tell(desk.digest_text(reports) if len(reports) > 1 else desk.report_text(reports[0]))
        return {"items": reports, "telegram": self.notify is not None}

    def daily_reports(self, connection: Connection) -> list[dict]:
        reports = desk.ensure_daily_reports(connection)
        if reports:
            for report in reports:
                self.log_work(report["employee"], "report", mode="daily", rating=report["rating"])
            self._tell(desk.digest_text(reports, "Laporan pagi tim"))
        return reports

    def telegram_digest(self, connection: Connection) -> dict:
        """Tegar sends the owner a fresh team summary on Telegram (nothing is stored)."""
        if self.notify is None:
            return {"sent": False}
        reports = [{"employee": e, "hours": 24, **desk.measure(connection, e)} for e in desk.EMPLOYEES]
        self.notify(desk.digest_text(reports, "Ringkasan dari Tegar"))
        self.log_work("tegar", "digest", count=len(reports))
        return {"sent": True}

    def _tell(self, text: str) -> None:
        if self.notify is None:
            return
        try:
            self.notify(text)
        except Exception as error:  # Telegram being down must never lose the report itself
            self.log_failure("tegar", "telegram", error)

    def start_github_sync(self) -> None:
        """Keep the portfolio fresh: re-sync the saved GitHub username when it is stale."""
        from .github_portfolio import load_portfolio, sync_portfolio
        from .settings_store import get_setting

        def loop() -> None:
            while True:
                try:
                    with open_db() as connection:
                        username = get_setting(connection, "ui_github")
                        synced = load_portfolio(connection).get("synced_at") or ""
                        age = (datetime.now(timezone.utc) - datetime.fromisoformat(synced)).total_seconds() if synced else None
                        if username and (age is None or age >= GITHUB_SYNC_SECONDS):
                            sync_portfolio(username, connection)
                            office_events.publish({"task": "github", "status": "synced", "employee": "cora"})
                except Exception as error:  # GitHub being down must never kill the thread
                    self.log_failure("cora", "github_sync", error)
                time.sleep(GITHUB_CHECK_SECONDS)

        threading.Thread(target=loop, name="office-github-sync", daemon=True).start()

    def start_daily_reports(self) -> None:
        def loop() -> None:
            while True:
                try:
                    with open_db() as connection:
                        self.daily_reports(connection)
                except Exception as error:  # never kill the thread, but never hide it either
                    self.log_failure(None, "report_loop", error)
                time.sleep(DAILY_CHECK_SECONDS)

        threading.Thread(target=loop, name="office-daily-reports", daemon=True).start()

    # ------------------------------------------------------------------ auto work

    def status(self) -> dict:
        next_in = None
        if self.auto and self.next_at is not None:
            next_in = max(0, int(self.next_at - self.clock()))
        return {"auto": self.auto, "busy": self.busy, "last": self.last, "next_in": next_in}

    def interval_seconds(self) -> float:
        raw = self._interval_seconds() if callable(self._interval_seconds) else self._interval_seconds
        return max(float(raw), MIN_INTERVAL_SECONDS)

    def set_auto(self, on: bool) -> None:
        self.auto = on
        if on and self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="office-auto-work", daemon=True)
            self._thread.start()
        self.log_work(None, "auto", mode="on" if on else "off")
        self._wake.set()

    def _loop(self) -> None:
        while True:
            if not self.auto:
                self._wake.wait()
                self._wake.clear()
                continue
            if self.next_at is None or self.clock() >= self.next_at:
                self.run_cycle()
                self.next_at = self.clock() + self.interval_seconds()
            self._wake.wait(timeout=max(1.0, self.next_at - self.clock()))
            self._wake.clear()

    def run_cycle(self) -> None:
        """Every scout searches once, then Cora drafts the best new matches."""
        try:
            with open_db() as connection:
                for source, hunt in self.hunters.items():
                    if not self.auto:
                        return
                    self.busy = source
                    started = self.clock()
                    with self.lock:
                        try:
                            result = hunt(connection)
                            self.last = {"source": source, "matched": result["matched"], "at": self.clock()}
                            self.log_work(
                                desk.SOURCE_OWNER.get(source), "hunt", source=source,
                                matched=result.get("matched"), inserted_count=result.get("inserted"),
                                duration_ms=int((self.clock() - started) * 1000),
                            )
                        except Exception as error:  # one broken source must not stop the others
                            self.last = {"source": source, "error": True, "at": self.clock()}
                            self.log_failure(
                                desk.SOURCE_OWNER.get(source), "hunt", error, source=source,
                                duration_ms=int((self.clock() - started) * 1000),
                            )
                self.busy = "draft"
                with self.lock:
                    try:
                        drafted = self.draft_next(connection)
                        self.last = {"source": "draft", "matched": drafted, "at": self.clock()}
                    except Exception as error:
                        self.last = {"source": "draft", "error": True, "at": self.clock()}
                        self.log_failure("cora", "draft", error)
                if self.proposal_writer is not None and self.auto:
                    self.busy = "proposal"
                    with self.lock:
                        try:
                            written = self.draft_proposals(connection)
                            self.last = {"source": "proposal", "matched": written, "at": self.clock()}
                        except Exception as error:
                            self.last = {"source": "proposal", "error": True, "at": self.clock()}
                            self.log_failure("cora", "proposal", error)
                if self.freelancer_bid is not None and self.auto:
                    self.busy = "bid"
                    with self.lock:
                        try:
                            result = run_auto_bids(connection, self.freelancer_bid, self._tell, self.freelancer_reconcile)
                            if result.get("sent") or result.get("error"):
                                self.log_work("faris", "auto_bid", count=result.get("sent", 0), status="error" if result.get("error") else "ok")
                        except Exception as error:  # a broken bid pass must not stop the work loop
                            self.log_failure("faris", "auto_bid", error)
        finally:
            self.busy = None


def _terms(terms) -> dict | None:
    if terms is None:
        return None
    return terms.as_dict()
