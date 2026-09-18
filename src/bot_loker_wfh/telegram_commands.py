"""Authenticated Telegram command handling for the MVP."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .status_transitions import (
    InvalidTransitionError,
    TransitionActor,
    transition_application_status,
)
from .telegram_auth import TelegramAuth, TelegramRequest


@dataclass(frozen=True)
class CommandResult:
    success: bool
    message: str


class TelegramCommandHandler:
    def __init__(self, connection: sqlite3.Connection, *, auth: TelegramAuth):
        self.connection = connection
        self.auth = auth

    def handle(self, request: TelegramRequest) -> CommandResult:
        decision = self.auth.authorize(request)
        if not decision.allowed:
            return CommandResult(False, decision.safe_response or "Unauthorized chat.")
        command, args = _parse_command(request.text)
        if command == "/lowongan":
            return CommandResult(True, self._list_jobs())
        if command == "/status":
            return self._change_status(args)
        if command == "/laporan":
            return CommandResult(True, self._report())
        return CommandResult(False, "Unknown command.")

    def _list_jobs(self) -> str:
        candidates = self.connection.execute(
            "SELECT id, title, company FROM jobs WHERE status = 'CANDIDATE' "
            "ORDER BY fetched_at DESC"
        ).fetchall()
        pending = self.connection.execute(
            "SELECT applications.id, jobs.title, jobs.company "
            "FROM applications JOIN jobs ON jobs.id = applications.job_id "
            "WHERE applications.status IN ('DRAFT_READY', 'PENDING_APPROVAL') "
            "ORDER BY applications.created_at DESC"
        ).fetchall()
        lines = ["Lowongan terbaru"]
        lines.extend(
            f"CANDIDATE {job_id}: {title} — {company}"
            for job_id, title, company in candidates
        )
        lines.extend(
            f"PENDING_APPROVAL {application_id}: {title} — {company}"
            for application_id, title, company in pending
        )
        return "\n".join(lines)

    def _change_status(self, args: list[str]) -> CommandResult:
        if len(args) != 2:
            return CommandResult(False, "Usage: /status [application_id] [status]")
        application_id, target_status = args
        try:
            transition_application_status(
                self.connection,
                application_id=application_id,
                to_status=target_status,
                actor=TransitionActor.USER,
            )
        except InvalidTransitionError as error:
            if str(error).startswith("Unknown application"):
                return CommandResult(False, "Application not found.")
            return CommandResult(False, "Invalid status transition.")
        return CommandResult(
            True, f"Application {application_id} status changed to {target_status}."
        )

    def _report(self) -> str:
        total_jobs = self.connection.execute(
            "SELECT COUNT(*) FROM jobs"
        ).fetchone()[0]
        candidates = self.connection.execute(
            "SELECT COUNT(*) FROM jobs WHERE status = 'CANDIDATE'"
        ).fetchone()[0]
        submitted = self.connection.execute(
            "SELECT COUNT(*) FROM applications WHERE status IN "
            "('SUBMITTED', 'VIEWED', 'INTERVIEW', 'OFFER', 'REJECTED_BY_COMPANY', 'NO_RESPONSE')"
        ).fetchone()[0]
        responses = self.connection.execute(
            "SELECT COUNT(*) FROM applications WHERE status IN "
            "('INTERVIEW', 'OFFER', 'REJECTED_BY_COMPANY')"
        ).fetchone()[0]
        return (
            "Laporan minggu berjalan\n"
            f"Lowongan ditemukan: {total_jobs}\n"
            f"Lolos filter: {candidates}\n"
            f"Dilamar: {submitted}\n"
            f"Mendapat respons: {responses}"
        )


def _parse_command(text: str | None) -> tuple[str, list[str]]:
    if not text or not text.strip():
        return "", []
    parts = text.strip().split()
    return parts[0].lower(), parts[1:]

