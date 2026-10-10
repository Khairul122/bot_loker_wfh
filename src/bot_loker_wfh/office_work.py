"""Owner workflow behind the 3D office: the auto-work cycle and the approval inbox.

Nothing is ever sent without the owner: the cycle only searches, scores and drafts.
Applying starts after an explicit approval, and the form filler stops before submit.
"""

from __future__ import annotations

import logging
import sqlite3
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .form_assist import FormAssistError, resolve_form_target, spawn_fill_form, spawn_fill_lead
from .lead_desk import lead_counts, list_leads, save_proposal, set_lead_status, undrafted_leads
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
PROPOSALS_PER_CYCLE = 3
MIN_INTERVAL_SECONDS = 5 * 60  # hard floor regardless of configured interval
DAILY_CHECK_SECONDS = 10 * 60
# owner's "update status" buttons on sent applications -> the real status transition
STATUS_ACTIONS = {
    "viewed": "VIEWED", "interview": "INTERVIEW", "offer": "OFFER",
    "rejected": "REJECTED_BY_COMPANY", "noresponse": "NO_RESPONSE",
}


@contextmanager
def open_db(path: Path) -> Iterator[sqlite3.Connection]:
    """Commit on success and always close (sqlite3's own context manager never closes)."""
    connection = sqlite3.connect(path, timeout=30)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


class OfficeWork:
    def __init__(
        self,
        database_path: Path,
        *,
        hunters: dict[str, Callable[[sqlite3.Connection], dict]],
        draft_service_for: Callable[[sqlite3.Connection], Any],
        form_assist_enabled: bool,
        interval_seconds: float | Callable[[], float],
        lock: threading.Lock,
        proposal_writer: Callable[..., str] | None = None,
        screener: Callable[[sqlite3.Connection], dict] | None = None,
        llm: Callable[[str], str] | None = None,
        notify: Callable[[str], None] | None = None,
        spawn: Callable[..., Any] = subprocess.Popen,
        clock: Callable[[], float] = time.time,
        logger: logging.Logger | None = None,
    ) -> None:
        self.database_path = database_path
        self.hunters = hunters
        self.draft_service_for = draft_service_for
        self.form_assist_enabled = form_assist_enabled
        self._interval_seconds = interval_seconds
        self.lock = lock  # shared with manual hunts: one search/draft at a time
        self.proposal_writer = proposal_writer
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

    def inbox(self, connection: sqlite3.Connection) -> dict:
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

    def draft_next(self, connection: sqlite3.Connection, limit: int = DRAFTS_PER_CYCLE) -> int:
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

    def decide(self, connection: sqlite3.Connection, application_id: str, action: str) -> dict:
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
                    "UPDATE applications SET last_status_check_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
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

    def _apply(self, connection: sqlite3.Connection, application_id: str) -> dict:
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
    def _status(connection: sqlite3.Connection, application_id: str) -> str | None:
        row = connection.execute(
            "SELECT status FROM applications WHERE id = ?", (application_id,)
        ).fetchone()
        return row[0] if row else None

    @staticmethod
    def _undrafted_count(connection: sqlite3.Connection) -> int:
        return connection.execute(
            "SELECT COUNT(*) FROM jobs j LEFT JOIN applications a ON a.job_id = j.id "
            "WHERE j.status = 'CANDIDATE' AND a.id IS NULL"
        ).fetchone()[0]

    # ------------------------------------------------------------------ freelance desk

    def draft_proposals(self, connection: sqlite3.Connection, limit: int = PROPOSALS_PER_CYCLE) -> int:
        """Cora pre-writes bids for the best new projects; they stay NEW until the owner acts."""
        lead_ids = undrafted_leads(connection, limit)
        for lead_id in lead_ids:
            self.proposal_writer(connection, lead_id, mark_interested=False)
        self.log_work("cora", "proposal", count=len(lead_ids))
        return len(lead_ids)

    def leads(self, connection: sqlite3.Connection, source: str | None, view: str = "all") -> dict:
        return {"items": list_leads(connection, source, view), "counts": lead_counts(connection, source),
                "browser_fill": self.form_assist_enabled}

    def lead_action(self, connection: sqlite3.Connection, lead_id: str, action: str, body: dict) -> dict:
        """interested | ignored | new | proposal | fill. Raises KeyError for unknown leads."""
        started = self.clock()
        employee, result = self._lead_action(connection, lead_id, action, body)
        self.log_work(
            employee, "lead", action=action, lead_id=lead_id, mode=result.get("mode"),
            duration_ms=int((self.clock() - started) * 1000),
        )
        return result

    def _lead_action(self, connection: sqlite3.Connection, lead_id: str, action: str, body: dict) -> tuple[str, dict]:
        if action in ("interested", "ignored", "new"):
            set_lead_status(connection, lead_id, action.upper())
            return "bimo", {"status": action.upper()}  # the bidding desk files the owner's verdict
        if action == "proposal":
            text = str(body.get("text") or "").strip()
            if text:
                save_proposal(connection, lead_id, text)
            else:
                text = self.proposal_writer(connection, lead_id)
            return "cora", {"proposal": text}
        if action == "fill":
            row = connection.execute("SELECT url, proposal FROM leads WHERE id = ?", (lead_id,)).fetchone()
            if row is None:
                raise KeyError(lead_id)
            engine = "playwright" if body.get("engine") == "playwright" else "browsermcp"
            if not self.form_assist_enabled or not (row[1] or "").strip():
                return "faris", {"mode": "manual", "url": row[0]}
            if self._lead_fill is not None and getattr(self._lead_fill, "poll", lambda: 0)() is None:
                return "faris", {"mode": "busy", "url": row[0]}
            self._lead_fill = spawn_fill_lead(lead_id, engine, spawn=self.spawn)
            self._watch(self._lead_fill, "faris", "fill", lead_id=lead_id, engine=engine)
            return "faris", {"mode": "form", "engine": engine, "url": row[0]}
        raise ValueError(f"unknown action: {action}")

    # ------------------------------------------------------------------ owner's office

    def request_reports(self, connection: sqlite3.Connection, employee: str) -> dict:
        """An employee (or 'all') writes a 24h report now; it is walked to the owner in 3D."""
        names = desk.EMPLOYEES if employee == "all" else (employee,)
        if any(name not in desk.ROLES for name in names):
            raise KeyError(employee)
        reports = [desk.create_report(connection, name) for name in names]
        for report in reports:
            self.log_work(report["employee"], "report", count=len(reports), rating=report["rating"])
        self._tell(desk.digest_text(reports) if len(reports) > 1 else desk.report_text(reports[0]))
        return {"items": reports, "telegram": self.notify is not None}

    def daily_reports(self, connection: sqlite3.Connection) -> list[dict]:
        reports = desk.ensure_daily_reports(connection)
        if reports:
            for report in reports:
                self.log_work(report["employee"], "report", mode="daily", rating=report["rating"])
            self._tell(desk.digest_text(reports, "Laporan pagi tim"))
        return reports

    def telegram_digest(self, connection: sqlite3.Connection) -> dict:
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

    def start_daily_reports(self) -> None:
        def loop() -> None:
            while True:
                try:
                    with open_db(self.database_path) as connection:
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
            with open_db(self.database_path) as connection:
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
        finally:
            self.busy = None
