"""ReportBuilder: Formats Telegram report and records form session to database."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any, Sequence

from bot_loker_wfh.form_agent.executor import ExecutionEvent
from bot_loker_wfh.form_agent.extractor import FormField
from bot_loker_wfh.form_agent.policy import RejectedAction


@dataclass(frozen=True)
class SessionRecordInput:
    application_id: str
    engine: str
    host: str
    mode: str
    page_number: int
    status: str
    company: str
    job_title: str
    all_fields: Sequence[FormField]
    executed_events: Sequence[ExecutionEvent]
    rejected_actions: Sequence[RejectedAction]
    has_captcha: bool = False
    tool_calls: int = 0
    error_code: str | None = None


class ReportBuilder:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path

    def build_report_text(self, record_input: SessionRecordInput) -> str:
        inp = record_input
        filled_labels = [
            e.label for e in inp.executed_events if e.action == "filled" and e.label
        ]
        ai_answered = [
            e.label for e in inp.executed_events if e.action == "ai_answered" and e.label
        ]

        # Gather manual fields (upload, rejected, failed, etc.)
        manual_items: list[str] = []
        for f in inp.all_fields:
            if f.field_class == "upload":
                manual_items.append(f"{f.label or 'Resume'} (upload file)")

        for rej in inp.rejected_actions:
            manual_items.append(f"{rej.action.ref} ({rej.reason})")

        for ev in inp.executed_events:
            if ev.action in {"error", "verify_failed"}:
                manual_items.append(f"{ev.label} ({ev.reason or 'gagal isi'})")

        sensitive_labels = [
            f.label for f in inp.all_fields if f.field_class == "sensitive" and f.label
        ]
        legal_labels = [
            f.label for f in inp.all_fields if f.field_class == "legal" and f.label
        ]

        captcha_text = "ada (harus diselesaikan manual)" if inp.has_captcha else "tidak ada"

        lines = [
            f"Form {inp.company} - {inp.job_title}",
            f"Engine: {inp.engine} | Halaman {inp.page_number} | Mode: {inp.mode}",
            (
                "Form TERKIRIM.\n"
                if inp.status == "submitted"
                else "Form TIDAK dikirim.\n"
            ),
        ]

        if filled_labels:
            lines.append(f"Terisi ({len(filled_labels)}): {', '.join(filled_labels)}\n")
        else:
            lines.append("Terisi (0): -\n")

        if ai_answered:
            lines.append(f"Dijawab AI, wajib cek ({len(ai_answered)}):")
            for a in ai_answered:
                lines.append(f"- {a}")
            lines.append("")

        if manual_items:
            lines.append(f"Perlu Anda isi/pilih ({len(manual_items)}):")
            for m in manual_items:
                lines.append(f"- {m}")
            lines.append("")

        if sensitive_labels:
            lines.append(
                f"Dilewati, data sensitif ({len(sensitive_labels)}): {', '.join(sensitive_labels)}"
            )

        if legal_labels:
            lines.append(
                f"Persetujuan legal ({len(legal_labels)}): {', '.join(legal_labels)}"
            )

        lines.append(f"\nCAPTCHA: {captcha_text}")
        if inp.status == "submitted":
            lines.append("\nStatus: bid berhasil dikirim.")
        else:
            lines.append(
                "\nLangkah: periksa semua field, upload CV, centang persetujuan, "
                f"tekan Submit sendiri, lalu ketik /dilamar {inp.application_id[:8]}"
            )

        return "\n".join(lines).strip()

    def record_session(self, record_input: SessionRecordInput) -> str:
        session_id = str(uuid.uuid4())
        if not self.db_path:
            return session_id

        inp = record_input
        filled_count = sum(
            1 for e in inp.executed_events if e.action == "filled"
        )
        ai_count = sum(
            1 for e in inp.executed_events if e.action == "ai_answered"
        )
        manual_count = len(inp.rejected_actions) + sum(
            1 for e in inp.executed_events if e.action in {"error", "verify_failed"}
        )
        skipped_count = sum(
            1
            for f in inp.all_fields
            if f.field_class in {"sensitive", "legal"}
        )

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO form_sessions (
                        id, application_id, engine, host, mode, page_number,
                        status, filled_count, ai_answer_count, manual_count,
                        skipped_protected_count, captcha, tool_calls, error_code
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        inp.application_id,
                        inp.engine,
                        inp.host,
                        inp.mode,
                        inp.page_number,
                        inp.status,
                        filled_count,
                        ai_count,
                        manual_count,
                        skipped_count,
                        1 if inp.has_captcha else 0,
                        inp.tool_calls,
                        inp.error_code,
                    ),
                )

                for ev in inp.executed_events:
                    conn.execute(
                        """
                        INSERT INTO form_field_events (
                            id, session_id, label, role, field_class,
                            action, source, reason, confidence
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid.uuid4()),
                            session_id,
                            ev.label,
                            ev.role,
                            ev.field_class,
                            ev.action,
                            ev.source,
                            ev.reason,
                            ev.confidence,
                        ),
                    )

                for rej in inp.rejected_actions:
                    conn.execute(
                        """
                        INSERT INTO form_field_events (
                            id, session_id, label, role, field_class,
                            action, source, reason, confidence
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid.uuid4()),
                            session_id,
                            rej.action.ref,
                            "",
                            "",
                            "rejected",
                            rej.action.source,
                            f"{rej.rule}:{rej.reason}",
                            rej.action.confidence,
                        ),
                    )

                conn.commit()
        except Exception:
            pass

        return session_id
