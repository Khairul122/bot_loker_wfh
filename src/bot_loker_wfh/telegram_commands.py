"""Authenticated Telegram command handling for the MVP."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .llm import fetch_9router_models_categorized
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

    def handle(self, request: TelegramRequest, router: Any | None = None) -> CommandResult:
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
        if command == "/model":
            return CommandResult(True, self._model_command(args, router))
        return CommandResult(False, "Unknown command.")

    def _model_command(self, args: list[str], router: Any | None = None) -> str:
        if args:
            target = args[0].strip()
            if target.lower() == "reset":
                if router and hasattr(router, "reset_model"):
                    router.reset_model()
                return "Model AI dikembalikan ke konfigurasi awal .env."
            if router and hasattr(router, "set_active_model"):
                router.set_active_model(target)
            return f"Model AI berhasil diubah ke: {target}."

        base_url = "http://localhost:20128/v1"
        api_key = "sk-dummy"
        if router and hasattr(router, "chain") and router.chain:
            first_prov = router.chain[0][0]
            if hasattr(first_prov, "base_url"):
                base_url = first_prov.base_url
            if hasattr(first_prov, "api_key") and first_prov.api_key:
                api_key = first_prov.api_key

        model_info = fetch_9router_models_categorized(base_url=base_url, api_key=api_key)

        active = getattr(router, "active_model", None) if router else None
        last = getattr(router, "last_result", None) if router else None

        lines = ["🤖 Model AI 9Router\n"]
        if active:
            lines.append(f"📌 Model Aktif: {active}")
        elif last:
            lines.append(f"📌 Model Terakhir: {last.provider}/{last.model}")

        if model_info.get("error"):
            lines.append(f"\n⚠️ (9Router tidak dapat dihubungi: {model_info['error']})")
        else:
            combos = model_info.get("combo", [])
            visions = model_info.get("vision", [])

            lines.append(f"\n📦 Combo Models ({len(combos)}):")
            if combos:
                for c in combos:
                    lines.append(f"• {c}")
            else:
                lines.append("• (tidak ada)")

            by_adapter: dict[str, list[str]] = {}
            for m in visions:
                adapter = m.split("/")[0] if "/" in m else "other"
                by_adapter.setdefault(adapter, []).append(m)

            lines.append(f"\n👁️ Vision Adapters ({len(by_adapter)}) & Models ({len(visions)}):")
            if by_adapter:
                for adapter, mlist in sorted(by_adapter.items()):
                    limit = 5 if len(mlist) <= 5 else 3
                    sample = ", ".join(mlist[:limit])
                    more = f" (+{len(mlist)-limit} lainnya)" if len(mlist) > limit else ""
                    lines.append(f"• [{adapter.upper()}]: {sample}{more}")
            else:
                lines.append("• (tidak ada)")

        lines.append("\n💡 Ketik '/model <nama>' untuk mengganti model aktif.")
        lines.append("💡 Ketik '/model reset' untuk mengembalikan ke default.")
        return "\n".join(lines)

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

        base = (
            "Laporan minggu berjalan\n"
            f"Lowongan ditemukan: {total_jobs}\n"
            f"Lolos filter: {candidates}\n"
            f"Dilamar: {submitted}\n"
            f"Mendapat respons: {responses}"
        )

        try:
            llm_calls_count = self.connection.execute(
                "SELECT COUNT(*), SUM(CASE WHEN status='success' THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) "
                "FROM llm_calls WHERE created_at >= strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-7 days')"
            ).fetchone()
            total_c, success_c, error_c = (
                llm_calls_count[0] or 0,
                llm_calls_count[1] or 0,
                llm_calls_count[2] or 0,
            )
            base += (
                f"\n\nAI 7 hari terakhir\n"
                f"- Panggilan: {total_c} (berhasil {success_c}, gagal {error_c})"
            )
        except Exception:
            pass

        try:
            form_sessions_count = self.connection.execute(
                "SELECT COUNT(*), AVG(filled_count), AVG(manual_count) "
                "FROM form_sessions WHERE started_at >= strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-7 days')"
            ).fetchone()
            s_count = form_sessions_count[0] or 0
            avg_filled = round(form_sessions_count[1] or 0, 1)
            avg_manual = round(form_sessions_count[2] or 0, 1)
            base += (
                f"\n\nForm 7 hari terakhir\n"
                f"- Sesi: {s_count}\n"
                f"- Rata-rata field terisi: {avg_filled}\n"
                f"- Rata-rata field manual: {avg_manual}"
            )
        except Exception:
            pass

        return base


def _parse_command(text: str | None) -> tuple[str, list[str]]:
    if not text or not text.strip():
        return "", []
    parts = text.strip().split()
    return parts[0].lower(), parts[1:]

