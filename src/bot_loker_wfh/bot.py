"""Long-running Telegram bot: polls updates and periodically sources jobs."""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Callable
from typing import Any

from .drafts import DraftService
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
    "/dilamar <application_id> - tandai sudah dikirim manual\n"
    "/status <application_id> <status> - ubah status manual\n"
    "/fetch - ambil lowongan baru sekarang\n"
    "/laporan - ringkasan statistik\n\n"
    "ID boleh diketik 8 karakter pertama saja. "
    "Tombol di bawah setiap lowongan lebih praktis."
)

NOTIFY_INTERVAL_SECONDS = 30 * 60
MAX_NOTIFICATIONS_PER_BATCH = 10
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
    ) -> None:
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

    def _safe_send(self, chat_id: int, text: str) -> None:
        try:
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
