"""Long-running Telegram bot: polls updates and periodically sources jobs."""

from __future__ import annotations

import logging
import os
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any

from .drafts import DraftService
from .form_assist import FormAssistError, resolve_form_target
from .leads import LeadService
from .logging_utils import StructuredLogger, sanitize_error
from .pipeline import JobPipeline
from .scheduler import JobScheduler
from .status_transitions import (
    InvalidTransitionError,
    TransitionActor,
    transition_application_status,
)
from .telegram_approval import TelegramApprovalHandler
from .telegram_auth import TelegramAuth, TelegramRequest
from .telegram_client import TelegramClient, TelegramError
from .telegram_commands import TelegramCommandHandler
from .telegram_notifications import TelegramNotificationService


HELP_TEXT = (
    "Bot Loker WFH\n\n"
    "/lowongan - daftar kandidat dan lamaran pending\n"
    "/siapkan <job_id> - buat draft lamaran untuk lowongan\n"
    "/setuju <application_id> - setujui lamaran\n"
    "/tolak <application_id> - tolak lamaran\n"
    "/isi <application_id> - buka form lamaran di browser & isi otomatis (tidak dikirim)\n"
    "/dilamar <application_id> - tandai sudah dikirim manual\n"
    "/lead - proyek freelance & peluang jual source code\n"
    "/status <application_id> <status> - ubah status manual\n"
    "/fetch - ambil lowongan baru sekarang\n"
    "/laporan - ringkasan statistik\n\n"
    "ID boleh diketik 8 karakter pertama saja. "
    "Tombol di bawah setiap lowongan lebih praktis."
)

NOTIFY_INTERVAL_SECONDS = 30 * 60
MAX_NOTIFICATIONS_PER_BATCH = 10
MAX_LEAD_NOTIFICATIONS_PER_BATCH = 5
POLL_TIMEOUT_SECONDS = 30
ERROR_BACKOFF_SECONDS = 5


class BotRunner:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        client: TelegramClient,
        allowed_chat_ids: frozenset[int],
        draft_service: DraftService,
        pipeline: JobPipeline,
        scheduler: JobScheduler | None,
        interval_seconds: int,
        logger: logging.Logger | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        form_assist_enabled: bool = False,
        spawn: Callable[..., Any] = subprocess.Popen,
        lead_service: LeadService | None = None,
    ) -> None:
        self.lead_service = lead_service
        self.form_assist_enabled = form_assist_enabled
        self.spawn = spawn
        self.connection = connection
        self.client = client
        self.allowed_chat_ids = allowed_chat_ids
        self.draft_service = draft_service
        self.pipeline = pipeline
        self.scheduler = scheduler
        self.interval_seconds = interval_seconds
        self.clock = clock
        self.sleep = sleep
        self.logger = StructuredLogger(logger or logging.getLogger(__name__))
        self.auth = TelegramAuth(allowed_chat_ids=allowed_chat_ids)
        self.commands = TelegramCommandHandler(connection, auth=self.auth)
        self.approvals = TelegramApprovalHandler(connection, auth=self.auth)

    # ------------------------------------------------------------------ loop

    def run_forever(self) -> None:
        greeting = "Bot aktif. Ketik /help untuk daftar perintah."
        if self.scheduler is not None:
            greeting += " Sedang mengambil lowongan pertama, bisa beberapa menit."
        for chat_id in sorted(self.allowed_chat_ids):
            self._safe_send(chat_id, greeting)
        self.logger.event("bot_started", status="running")

        offset: int | None = None
        next_cycle = self.clock()
        next_notify = self.clock() + NOTIFY_INTERVAL_SECONDS
        while True:
            now = self.clock()
            if now >= next_cycle:
                self._safe_cycle()
                next_cycle = self.clock() + self.interval_seconds
                next_notify = self.clock() + NOTIFY_INTERVAL_SECONDS
            elif now >= next_notify:
                self._safe_notify()
                next_notify = self.clock() + NOTIFY_INTERVAL_SECONDS

            try:
                updates = self.client.get_updates(offset, timeout=POLL_TIMEOUT_SECONDS)
            except TelegramError:
                self.logger.warning("poll_failed", status="error", error_code="network_error")
                self.sleep(ERROR_BACKOFF_SECONDS)
                continue
            for update in updates:
                offset = int(update["update_id"]) + 1
                try:
                    self.handle_update(update)
                except Exception as error:
                    self.logger.error(
                        "update_failed", status="error", error_code=sanitize_error(error)
                    )

    def run_cycle(self) -> dict[str, int]:
        """Fetch (when enabled), score/filter, then notify. Returns counts."""
        summary: dict[str, int] = {}
        if self.scheduler is not None:
            for source, inserted in self.scheduler.run_once().items():
                summary[f"{source}_inserted"] = inserted
        summary.update(self.pipeline.process_discovered())
        summary["notified"] = self.notify_candidates()
        if self.lead_service is not None and self.scheduler is not None:
            summary["lead_new"] = sum(self.lead_service.collect().values())
            summary["lead_notified"] = self.notify_leads()
        self.logger.event(
            "cycle_complete", status="success", inserted_count=summary["candidate"]
        )
        return summary

    def _safe_cycle(self) -> None:
        try:
            self.run_cycle()
        except Exception as error:
            self.logger.error(
                "cycle_failed", status="error", error_code=sanitize_error(error)
            )

    def _safe_notify(self) -> None:
        try:
            self.notify_candidates()
            self.notify_leads()
        except Exception as error:
            self.logger.error(
                "notify_failed", status="error", error_code=sanitize_error(error)
            )

    def notify_candidates(self) -> int:
        """Send not-yet-notified candidates (best scored first); returns count."""
        job_ids = [
            row[0]
            for row in self.connection.execute(
                "SELECT id FROM jobs WHERE status = 'CANDIDATE' AND notified_at IS NULL "
                "ORDER BY relevance_score DESC, fetched_at DESC LIMIT ?",
                (MAX_NOTIFICATIONS_PER_BATCH,),
            ).fetchall()
        ]
        sent = 0
        for job_id in job_ids:
            try:
                for chat_id in sorted(self.allowed_chat_ids):
                    message = TelegramNotificationService(
                        self.connection, chat_id=chat_id
                    ).candidate_message(job_id)
                    if message is not None:
                        self.client.send_message(message)
            except TelegramError:
                break
            self.connection.execute(
                "UPDATE jobs SET notified_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') "
                "WHERE id = ?",
                (job_id,),
            )
            self.connection.commit()
            sent += 1
        return sent

    def notify_leads(self) -> int:
        """Send not-yet-notified freelance leads (best scored first); returns count."""
        if self.lead_service is None:
            return 0
        sent = 0
        for lead_id in self.lead_service.unnotified_ids(MAX_LEAD_NOTIFICATIONS_PER_BATCH):
            try:
                for chat_id in sorted(self.allowed_chat_ids):
                    message = self.lead_service.message(lead_id, chat_id)
                    if message is not None:
                        self.client.send_message(message)
            except TelegramError:
                break
            self.lead_service.mark_notified(lead_id)
            sent += 1
        return sent

    # -------------------------------------------------------------- handlers

    def handle_update(self, update: dict[str, Any]) -> None:
        if "callback_query" in update:
            self._handle_callback(update["callback_query"])
        elif "message" in update:
            self._handle_message(update["message"])

    def _handle_message(self, message: dict[str, Any]) -> None:
        text = message.get("text")
        if not text:
            return
        chat_id = int(message["chat"]["id"])
        request = TelegramRequest(chat_id=chat_id, text=text)
        decision = self.auth.authorize(request)
        if not decision.allowed:
            self._safe_send(chat_id, decision.safe_response or "Unauthorized chat.")
            return

        command, args = _split_command(text)
        if command in {"/start", "/help"}:
            self._safe_send(chat_id, HELP_TEXT)
        elif command in {"/lowongan", "/status", "/laporan"}:
            self._safe_send(chat_id, self.commands.handle(request).message)
        elif command == "/siapkan":
            self._prepare(chat_id, self._resolve("jobs", args))
        elif command in {"/setuju", "/tolak"}:
            self._decide(
                chat_id,
                "approve" if command == "/setuju" else "reject",
                self._resolve("applications", args),
            )
        elif command == "/lead":
            self._safe_send(
                chat_id,
                self.lead_service.list_text() if self.lead_service else "Fitur lead belum aktif.",
            )
        elif command == "/isi":
            self._fill_form(chat_id, self._resolve("applications", args))
        elif command == "/dilamar":
            self._mark_applied(chat_id, self._resolve("applications", args))
        elif command == "/fetch":
            self._manual_fetch(chat_id)
        else:
            self._safe_send(chat_id, "Perintah tidak dikenal. Ketik /help.")

    def _handle_callback(self, query: dict[str, Any]) -> None:
        chat_id = int(query["message"]["chat"]["id"])
        query_id = str(query["id"])
        data = str(query.get("data") or "")
        decision = self.auth.authorize(TelegramRequest(chat_id=chat_id, callback_data=data))
        if not decision.allowed:
            self._safe_answer(query_id, decision.safe_response or "Unauthorized chat.")
            return

        parts = data.split(":")
        action = parts[0]
        target = parts[1] if len(parts) > 1 else ""
        if action == "prepare" and target:
            self._safe_answer(query_id, "Menyiapkan draft...")
            self._prepare(chat_id, target)
        elif action == "lead" and target and len(parts) == 3:
            self._handle_lead_button(query, target, parts[2])
        elif action == "fill" and target:
            self._safe_answer(query_id, "Membuka browser...")
            self._fill_form(chat_id, target)
        elif action in {"approve", "reject"}:
            result = self.approvals.handle(
                TelegramRequest(chat_id=chat_id, callback_data=data)
            )
            self._safe_answer(query_id, result.message)
            if result.success:
                self._after_decision(chat_id, action, target)
        else:
            self._safe_answer(query_id, "Invalid request.")

    # ------------------------------------------------------------- actions

    def _handle_lead_button(
        self, query: dict[str, Any], lead_id: str, status: str
    ) -> None:
        query_id = str(query["id"])
        if self.lead_service is None or status not in {"INTERESTED", "IGNORED"}:
            self._safe_answer(query_id, "Invalid request.")
            return
        if not self.lead_service.set_status(lead_id, status):
            self._safe_answer(query_id, "Lead tidak ditemukan.")
            return
        label = (
            "MINAT - tersimpan, lihat semua dengan /lead"
            if status == "INTERESTED"
            else "DIABAIKAN"
        )
        self._safe_answer(query_id, "Ditandai minat." if status == "INTERESTED" else "Diabaikan.")
        # Rewrite the card so the click is visible: status line, no more buttons.
        message = query.get("message") or {}
        if message.get("message_id") and message.get("text"):
            try:
                self.client.edit_message_text(
                    int(message["chat"]["id"]),
                    int(message["message_id"]),
                    f"{message['text']}\n\n{'✅' if status == 'INTERESTED' else '🚫'} {label}",
                )
            except TelegramError:
                self.logger.warning("edit_failed", status="error", error_code="network_error")

    def _prepare(self, chat_id: int, job_id: str | None) -> None:
        if job_id is None:
            self._safe_send(chat_id, "Job tidak ditemukan. Gunakan ID dari /lowongan.")
            return
        result = self.draft_service.prepare(job_id)
        if result.application_id is None:
            reason = {
                "job_not_found": "Job tidak ditemukan.",
                "job_not_candidate": "Job ini bukan kandidat.",
            }.get(result.error_code or "", "Draft gagal dibuat.")
            self._safe_send(chat_id, reason)
            return
        if result.application_status == "PENDING_APPROVAL":
            message = TelegramNotificationService(
                self.connection, chat_id=chat_id
            ).approval_message(result.application_id)
            if message is not None:
                self._safe_send_message(message)
                return
        self._safe_send(
            chat_id,
            f"Lamaran {result.application_id} sudah ada dengan status "
            f"{result.application_status}.",
        )

    def _decide(self, chat_id: int, action: str, application_id: str | None) -> None:
        if application_id is None:
            self._safe_send(chat_id, "Application tidak ditemukan.")
            return
        result = self.approvals.handle(
            TelegramRequest(
                chat_id=chat_id,
                callback_data=f"{action}:{application_id}:PENDING_APPROVAL",
            )
        )
        self._safe_send(chat_id, result.message)
        if result.success:
            self._after_decision(chat_id, action, application_id)

    def _after_decision(self, chat_id: int, action: str, application_id: str) -> None:
        if action != "approve":
            return
        row = self.connection.execute(
            "SELECT jobs.title, jobs.company, jobs.apply_url FROM applications "
            "JOIN jobs ON jobs.id = applications.job_id WHERE applications.id = ?",
            (application_id,),
        ).fetchone()
        if row is None:
            return
        self._safe_send(
            chat_id,
            f"Disetujui: {row[0]} — {row[1]}\n"
            f"Kirim lamaran lewat link ini:\n{row[2]}\n\n"
            f"Setelah terkirim, ketik:\n/dilamar {application_id}",
        )

    def _fill_form(self, chat_id: int, application_id: str | None) -> None:
        if not self.form_assist_enabled:
            self._safe_send(
                chat_id,
                "Fitur isi form aktif hanya jika bot berjalan di laptop Anda "
                "dengan FORM_ASSIST_ENABLED=true.",
            )
            return
        if application_id is None:
            self._safe_send(chat_id, "Application tidak ditemukan.")
            return
        status = self.connection.execute(
            "SELECT status FROM applications WHERE id = ?", (application_id,)
        ).fetchone()
        if status is None or status[0] != "APPROVED":
            self._safe_send(chat_id, "Setujui lamaran dulu (harus berstatus APPROVED).")
            return
        try:
            resolve_form_target(self.connection, application_id)
        except FormAssistError as error:
            self._safe_send(chat_id, str(error))
            return
        try:
            self.spawn(
                [
                    sys.executable, "-m", "bot_loker_wfh",
                    "fill-form", "--application-id", application_id,
                ],
                cwd=os.getcwd(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            self._safe_send(chat_id, "Gagal menjalankan pengisi form.")
            return
        self._safe_send(chat_id, "Membuka browser di laptop Anda, mohon tunggu...")

    def _mark_applied(self, chat_id: int, application_id: str | None) -> None:
        if application_id is None:
            self._safe_send(chat_id, "Application tidak ditemukan.")
            return
        try:
            row = self.connection.execute(
                "SELECT status FROM applications WHERE id = ?", (application_id,)
            ).fetchone()
            if row is None or row[0] != "APPROVED":
                self._safe_send(chat_id, "Hanya lamaran berstatus APPROVED yang bisa ditandai.")
                return
            transition_application_status(
                self.connection,
                application_id=application_id,
                to_status="SUBMITTED",
                actor=TransitionActor.USER,
                manual_correction=True,
                reason="applied manually by user via Telegram",
            )
        except InvalidTransitionError:
            self._safe_send(chat_id, "Status tidak bisa diubah.")
            return
        self.connection.execute(
            "UPDATE applications SET method = 'manual', "
            "submitted_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
            (application_id,),
        )
        self.connection.commit()
        self._safe_send(chat_id, "Ditandai sebagai SUBMITTED. Semoga sukses!")

    def _manual_fetch(self, chat_id: int) -> None:
        self._safe_send(chat_id, "Mengambil lowongan, mohon tunggu...")
        try:
            summary = self.run_cycle()
        except Exception as error:
            self._safe_send(chat_id, f"Fetch gagal: {sanitize_error(error)}")
            return
        self._safe_send(
            chat_id,
            "Selesai. "
            + ", ".join(f"{key}={value}" for key, value in summary.items()),
        )

    def _resolve(self, table: str, args: list[str]) -> str | None:
        """Resolve a full id or unique prefix; None when missing or ambiguous."""
        if not args:
            return None
        prefix = args[0].strip()
        if not prefix or any(char in prefix for char in "%_"):
            return None
        rows = self.connection.execute(
            f"SELECT id FROM {table} WHERE id LIKE ? LIMIT 2", (f"{prefix}%",)
        ).fetchall()
        return str(rows[0][0]) if len(rows) == 1 else None

    # ------------------------------------------------------------- sending

    def _safe_send(
        self,
        chat_id: int,
        text: str,
        keyboard: tuple[tuple[tuple[str, str], ...], ...] = (),
    ) -> None:
        try:
            if keyboard:
                self.client.send_text(chat_id, text, keyboard)
            else:
                self.client.send_text(chat_id, text)
        except TelegramError:
            self.logger.warning("send_failed", status="error", error_code="network_error")

    def _safe_send_message(self, message: Any) -> None:
        try:
            self.client.send_message(message)
        except TelegramError:
            self.logger.warning("send_failed", status="error", error_code="network_error")

    def _safe_answer(self, query_id: str, text: str) -> None:
        try:
            self.client.answer_callback(query_id, text)
        except TelegramError:
            self.logger.warning("answer_failed", status="error", error_code="network_error")


def _split_command(text: str) -> tuple[str, list[str]]:
    parts = text.strip().split()
    if not parts:
        return "", []
    return parts[0].split("@")[0].lower(), parts[1:]
