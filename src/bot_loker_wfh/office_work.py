"""Owner workflow behind the 3D office: the auto-work cycle and the approval inbox.

Nothing is ever sent without the owner: the cycle only searches, scores and drafts.
Applying starts after an explicit approval, and the form filler stops before submit.
"""

from __future__ import annotations

import sqlite3
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .form_assist import FormAssistError, resolve_form_target, spawn_fill_form, spawn_fill_lead
from .lead_desk import list_leads, save_proposal, set_lead_status, undrafted_leads
from .status_transitions import (
    InvalidTransitionError,
    TransitionActor,
    mark_applied_manually,
    transition_application_status,
)

DRAFTS_PER_CYCLE = 3
PROPOSALS_PER_CYCLE = 3


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
        interval_seconds: int,
        lock: threading.Lock,
        proposal_writer: Callable[..., str] | None = None,
        spawn: Callable[..., Any] = subprocess.Popen,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.database_path = database_path
        self.hunters = hunters
        self.draft_service_for = draft_service_for
        self.form_assist_enabled = form_assist_enabled
        self.interval_seconds = interval_seconds
        self.lock = lock  # shared with manual hunts: one search/draft at a time
        self.proposal_writer = proposal_writer
        self._lead_fill: Any = None  # the running fill-lead process, if any
        self.spawn = spawn
        self.clock = clock
        self.auto = False
        self.busy: str | None = None
        self.last: dict | None = None
        self.next_at: float | None = None
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ inbox

    def inbox(self, connection: sqlite3.Connection) -> dict:
        rows = connection.execute(
            "SELECT a.id, a.status, j.title, j.company, j.location, j.apply_url, "
            "j.relevance_score, a.cover_letter FROM applications a JOIN jobs j ON j.id = a.job_id "
            "WHERE a.status IN ('PENDING_APPROVAL', 'APPROVED') "
            "ORDER BY j.relevance_score DESC, a.created_at DESC"
        ).fetchall()
        items = [
            dict(zip(("id", "status", "title", "company", "location", "url", "score", "letter"), row))
            for row in rows
        ]
        return {
            "pending": [i for i in items if i["status"] == "PENDING_APPROVAL"],
            "approved": [i for i in items if i["status"] == "APPROVED"],
            "waiting": self._undrafted_count(connection),
            "form_assist": self.form_assist_enabled,
        }

    def draft_next(self, connection: sqlite3.Connection, limit: int = DRAFTS_PER_CYCLE) -> int:
        """Let Cora draft letters for the best-scored candidates that have none yet."""
        job_ids = [
            row[0]
            for row in connection.execute(
                "SELECT j.id FROM jobs j LEFT JOIN applications a ON a.job_id = j.id "
                "WHERE j.status = 'CANDIDATE' AND a.id IS NULL "
                "ORDER BY j.relevance_score DESC, j.fetched_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        ]
        service = self.draft_service_for(connection)
        return sum(
            1 for job_id in job_ids if service.prepare(job_id).application_status == "PENDING_APPROVAL"
        )

    def decide(self, connection: sqlite3.Connection, application_id: str, action: str) -> dict:
        """approve | reject | apply | applied. Raises InvalidTransitionError when stale."""
        if action in ("approve", "reject"):
            transition_application_status(
                connection,
                application_id=application_id,
                to_status="APPROVED" if action == "approve" else "REJECTED_BY_USER",
                actor=TransitionActor.USER,
            )
            if action == "reject":
                return {"status": "REJECTED_BY_USER"}
            return {"status": "APPROVED", **self._apply(connection, application_id)}
        if action == "apply":
            if self._status(connection, application_id) != "APPROVED":
                raise InvalidTransitionError("approve first")
            return {"status": "APPROVED", **self._apply(connection, application_id)}
        if action == "applied":
            mark_applied_manually(connection, application_id, via="3D office")
            return {"status": "SUBMITTED"}
        raise InvalidTransitionError(f"unknown action: {action}")

    def _apply(self, connection: sqlite3.Connection, application_id: str) -> dict:
        url = connection.execute(
            "SELECT j.apply_url FROM applications a JOIN jobs j ON j.id = a.job_id WHERE a.id = ?",
            (application_id,),
        ).fetchone()[0]
        if self.form_assist_enabled:
            try:
                resolve_form_target(connection, application_id)
                spawn_fill_form(application_id, spawn=self.spawn)
                return {"mode": "form", "url": url}
            except (FormAssistError, OSError):
                pass  # unsupported form or launcher failed: the owner applies by hand
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
        return len(lead_ids)

    def leads(self, connection: sqlite3.Connection, source: str | None) -> dict:
        return {"items": list_leads(connection, source), "browser_fill": self.form_assist_enabled}

    def lead_action(self, connection: sqlite3.Connection, lead_id: str, action: str, body: dict) -> dict:
        """interested | ignored | new | proposal | fill. Raises KeyError for unknown leads."""
        if action in ("interested", "ignored", "new"):
            set_lead_status(connection, lead_id, action.upper())
            return {"status": action.upper()}
        if action == "proposal":
            text = str(body.get("text") or "").strip()
            if text:
                save_proposal(connection, lead_id, text)
            else:
                text = self.proposal_writer(connection, lead_id)
            return {"proposal": text}
        if action == "fill":
            row = connection.execute("SELECT url, proposal FROM leads WHERE id = ?", (lead_id,)).fetchone()
            if row is None:
                raise KeyError(lead_id)
            engine = "playwright" if body.get("engine") == "playwright" else "browsermcp"
            if not self.form_assist_enabled or not (row[1] or "").strip():
                return {"mode": "manual", "url": row[0]}
            if self._lead_fill is not None and getattr(self._lead_fill, "poll", lambda: 0)() is None:
                return {"mode": "busy", "url": row[0]}
            self._lead_fill = spawn_fill_lead(lead_id, engine, spawn=self.spawn)
            return {"mode": "form", "engine": engine, "url": row[0]}
        raise ValueError(f"unknown action: {action}")

    # ------------------------------------------------------------------ auto work

    def status(self) -> dict:
        next_in = None
        if self.auto and self.next_at is not None:
            next_in = max(0, int(self.next_at - self.clock()))
        return {"auto": self.auto, "busy": self.busy, "last": self.last, "next_in": next_in}

    def set_auto(self, on: bool) -> None:
        self.auto = on
        if on and self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="office-auto-work", daemon=True)
            self._thread.start()
        self._wake.set()

    def _loop(self) -> None:
        while True:
            if not self.auto:
                self._wake.wait()
                self._wake.clear()
                continue
            if self.next_at is None or self.clock() >= self.next_at:
                self.run_cycle()
                self.next_at = self.clock() + self.interval_seconds
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
                    with self.lock:
                        try:
                            result = hunt(connection)
                            self.last = {"source": source, "matched": result["matched"], "at": self.clock()}
                        except Exception:  # one broken source must not stop the others
                            self.last = {"source": source, "error": True, "at": self.clock()}
                self.busy = "draft"
                with self.lock:
                    try:
                        drafted = self.draft_next(connection)
                        self.last = {"source": "draft", "matched": drafted, "at": self.clock()}
                    except Exception:
                        self.last = {"source": "draft", "error": True, "at": self.clock()}
                if self.proposal_writer is not None and self.auto:
                    self.busy = "proposal"
                    with self.lock:
                        try:
                            written = self.draft_proposals(connection)
                            self.last = {"source": "proposal", "matched": written, "at": self.clock()}
                        except Exception:
                            self.last = {"source": "proposal", "error": True, "at": self.clock()}
        finally:
            self.busy = None
