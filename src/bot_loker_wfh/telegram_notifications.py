"""Telegram notification payloads for manual review."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class TelegramButton:
    label: str
    callback_data: str


@dataclass(frozen=True)
class TelegramMessage:
    chat_id: int
    text: str
    inline_keyboard: tuple[tuple[TelegramButton, ...], ...]


class TelegramNotificationService:
    def __init__(self, connection: sqlite3.Connection, *, chat_id: int):
        self.connection = connection
        self.chat_id = chat_id

    def candidate_notifications(self) -> list[TelegramMessage]:
        rows = self.connection.execute(
            "SELECT id, title, company, location, source, apply_url, filtered_reason "
            "FROM jobs WHERE status = 'CANDIDATE' ORDER BY fetched_at DESC"
        ).fetchall()
        return [self._candidate_message(row) for row in rows]

    def pending_approval_notifications(self) -> list[TelegramMessage]:
        rows = self.connection.execute(
            "SELECT applications.id, jobs.title, jobs.company, jobs.location, "
            "jobs.source, jobs.apply_url, applications.cover_letter, applications.cv_summary "
            "FROM applications JOIN jobs ON jobs.id = applications.job_id "
            "WHERE applications.status = 'PENDING_APPROVAL' "
            "ORDER BY applications.created_at DESC"
        ).fetchall()
        return [self._approval_message(row) for row in rows]

    def candidate_message(self, job_id: str) -> TelegramMessage | None:
        row = self.connection.execute(
            "SELECT id, title, company, location, source, apply_url, filtered_reason "
            "FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        return self._candidate_message(row) if row else None

    def approval_message(self, application_id: str) -> TelegramMessage | None:
        row = self.connection.execute(
            "SELECT applications.id, jobs.title, jobs.company, jobs.location, "
            "jobs.source, jobs.apply_url, applications.cover_letter, applications.cv_summary "
            "FROM applications JOIN jobs ON jobs.id = applications.job_id "
            "WHERE applications.id = ?",
            (application_id,),
        ).fetchone()
        return self._approval_message(row) if row else None

    def _candidate_message(self, row: tuple[object, ...]) -> TelegramMessage:
        job_id, title, company, location, source, apply_url, filtered_reason = row
        reason_line = (
            f"\nCatatan: {filtered_reason}" if filtered_reason else ""
        )
        return TelegramMessage(
            chat_id=self.chat_id,
            text=(
                f"Lowongan candidate\n"
                f"Posisi: {title}\n"
                f"Perusahaan: {company}\n"
                f"Lokasi: {location or '-'}\n"
                f"Sumber: {source}\n"
                f"Apply: {apply_url}"
                f"{reason_line}"
            ),
            inline_keyboard=(
                (
                    TelegramButton(
                        "Siapkan draft", f"prepare:{job_id}:CANDIDATE"
                    ),
                ),
            ),
        )

    def _approval_message(self, row: tuple[object, ...]) -> TelegramMessage:
        application_id, title, company, location, source, apply_url, cover_letter, cv_summary = row
        return TelegramMessage(
            chat_id=self.chat_id,
            text=(
                f"Review lamaran\n"
                f"Posisi: {title}\n"
                f"Perusahaan: {company}\n"
                f"Lokasi: {location or '-'}\n"
                f"Sumber: {source}\n"
                f"Apply: {apply_url}\n\n"
                f"Cover letter:\n{cover_letter}\n\n"
                f"CV summary:\n{cv_summary}"
            ),
            inline_keyboard=(
                (
                    TelegramButton(
                        "Setujui", f"approve:{application_id}:PENDING_APPROVAL"
                    ),
                    TelegramButton(
                        "Tolak", f"reject:{application_id}:PENDING_APPROVAL"
                    ),
                ),
            ),
        )

