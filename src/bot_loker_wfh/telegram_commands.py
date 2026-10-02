"""Authenticated Telegram command handling for the MVP."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .filters import FilterConfig, FilterRepository
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
        if command == "/filter":
            return CommandResult(True, self._filter_command(args))
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

    def _filter_command(self, args: list[str]) -> str:
        repo = FilterRepository(self.connection)
        try:
            cfg = repo.get()
        except Exception:
            return "Konfigurasi filter tidak ditemukan."

        if not args:
            bids_text = f"{cfg.max_bids} bid" if cfg.max_bids is not None else "Tanpa batas (semua bid diambil)"
            lines = [
                "🔍 Filter Scraping Lowongan & Lead Aktif:\n",
                f"🎯 Role Keywords ({len(cfg.role_keywords)}):",
                ", ".join(cfg.role_keywords) if cfg.role_keywords else "(kosong)",
                "",
                f"🚫 Exclusion Keywords ({len(cfg.exclusion_keywords)}):",
                ", ".join(cfg.exclusion_keywords) if cfg.exclusion_keywords else "(kosong)",
                "",
                f"📊 Min Relevance Score: {cfg.min_relevance_score:.2f}",
                f"⏱️ Max Posting Age: {cfg.max_posting_age_days} hari",
                f"💼 Max Jumlah Bid (Lead Freelance): {bids_text}",
                "",
                "💡 Perintah Mengubah Filter:",
                "• /filter role laravel, python, react (ganti kata kunci posisi)",
                "• /filter addrole golang (tambah kata kunci posisi)",
                "• /filter exclude unpaid, intern (ganti kata kunci blokir)",
                "• /filter addexclude senior (tambah kata kunci blokir)",
                "• /filter score 0.5 (set min score 0.0 - 1.0)",
                "• /filter age 7 (set max umur lowongan dalam hari)",
                "• /filter bid 30 (set max jumlah bid untuk proyek freelance)",
                "• /filter bid 0 (atau 'off' untuk matikan filter jumlah bid)",
                "• /filter reset (kembalikan ke filter awal)"
            ]
            return "\n".join(lines)

        sub = args[0].lower()
        rest = " ".join(args[1:]).strip()

        DEFAULT_ROLES = (
            "laravel", "flutter", "nestjs", "react", "python", "backend",
            "full stack", "fullstack", "mobile developer", "software engineer",
            "software developer", "web developer", "programmer"
        )
        DEFAULT_EXCLUSIONS = ("unpaid", "commission only", "equity only", "must relocate")

        if sub == "reset":
            new_cfg = FilterConfig(
                role_keywords=DEFAULT_ROLES,
                exclusion_keywords=DEFAULT_EXCLUSIONS,
                min_relevance_score=0.65,
                max_posting_age_days=14,
                no_response_after_days=cfg.no_response_after_days,
                max_bids=None,
            )
            repo.update(new_cfg)
            return "Filter berhasil dikembalikan ke posisi awal (default)."

        if sub in {"role", "roles"}:
            if not rest:
                return "Harap berikan kata kunci posisi. Contoh: /filter role laravel, python, react"
            items = tuple(dict.fromkeys(k.strip().lower() for k in rest.replace(",", " ").split() if k.strip()))
            if not items:
                return "Kata kunci tidak boleh kosong."
            new_cfg = FilterConfig(
                role_keywords=items,
                exclusion_keywords=cfg.exclusion_keywords,
                min_relevance_score=cfg.min_relevance_score,
                max_posting_age_days=cfg.max_posting_age_days,
                no_response_after_days=cfg.no_response_after_days,
                max_bids=cfg.max_bids,
            )
            repo.update(new_cfg)
            return f"Role keywords diperbarui ({len(items)} kata):\n" + ", ".join(items)

        if sub in {"addrole", "addroles"}:
            if not rest:
                return "Harap berikan kata kunci posisi yang ingin ditambahkan. Contoh: /filter addrole golang"
            new_items = [k.strip().lower() for k in rest.replace(",", " ").split() if k.strip()]
            combined = tuple(dict.fromkeys(list(cfg.role_keywords) + new_items))
            new_cfg = FilterConfig(
                role_keywords=combined,
                exclusion_keywords=cfg.exclusion_keywords,
                min_relevance_score=cfg.min_relevance_score,
                max_posting_age_days=cfg.max_posting_age_days,
                no_response_after_days=cfg.no_response_after_days,
                max_bids=cfg.max_bids,
            )
            repo.update(new_cfg)
            return f"Role keywords berhasil ditambahkan ({len(combined)} total):\n" + ", ".join(combined)

        if sub in {"exclude", "exclusions"}:
            if not rest:
                return "Harap berikan kata kunci pengecualian. Contoh: /filter exclude unpaid, intern"
            items = tuple(dict.fromkeys(k.strip().lower() for k in rest.replace(",", " ").split() if k.strip()))
            new_cfg = FilterConfig(
                role_keywords=cfg.role_keywords,
                exclusion_keywords=items,
                min_relevance_score=cfg.min_relevance_score,
                max_posting_age_days=cfg.max_posting_age_days,
                no_response_after_days=cfg.no_response_after_days,
                max_bids=cfg.max_bids,
            )
            repo.update(new_cfg)
            return f"Exclusion keywords diperbarui ({len(items)} kata):\n" + (", ".join(items) if items else "(kosong)")

        if sub in {"addexclude", "addexclusions"}:
            if not rest:
                return "Harap berikan kata kunci pengecualian yang ingin ditambahkan."
            new_items = [k.strip().lower() for k in rest.replace(",", " ").split() if k.strip()]
            combined = tuple(dict.fromkeys(list(cfg.exclusion_keywords) + new_items))
            new_cfg = FilterConfig(
                role_keywords=cfg.role_keywords,
                exclusion_keywords=combined,
                min_relevance_score=cfg.min_relevance_score,
                max_posting_age_days=cfg.max_posting_age_days,
                no_response_after_days=cfg.no_response_after_days,
                max_bids=cfg.max_bids,
            )
            repo.update(new_cfg)
            return f"Exclusion keywords berhasil ditambahkan ({len(combined)} total):\n" + ", ".join(combined)

        if sub in {"score", "minscore"}:
            try:
                val = float(rest)
                if not (0.0 <= val <= 1.0):
                    raise ValueError()
            except ValueError:
                return "Skor relevansi harus berupa angka desimal antara 0.0 dan 1.0. Contoh: /filter score 0.5"
            new_cfg = FilterConfig(
                role_keywords=cfg.role_keywords,
                exclusion_keywords=cfg.exclusion_keywords,
                min_relevance_score=val,
                max_posting_age_days=cfg.max_posting_age_days,
                no_response_after_days=cfg.no_response_after_days,
                max_bids=cfg.max_bids,
            )
            repo.update(new_cfg)
            return f"Min relevance score diubah menjadi: {val:.2f}"

        if sub in {"age", "maxage"}:
            try:
                val = int(rest)
                if val < 0:
                    raise ValueError()
            except ValueError:
                return "Max age harus berupa angka bulat positif (hari). Contoh: /filter age 7"
            new_cfg = FilterConfig(
                role_keywords=cfg.role_keywords,
                exclusion_keywords=cfg.exclusion_keywords,
                min_relevance_score=cfg.min_relevance_score,
                max_posting_age_days=val,
                no_response_after_days=cfg.no_response_after_days,
                max_bids=cfg.max_bids,
            )
            repo.update(new_cfg)
            return f"Max posting age diubah menjadi: {val} hari"

        if sub in {"bid", "bids", "maxbid", "maxbids"}:
            if not rest:
                return "Harap berikan angka jumlah bid. Contoh: /filter bid 30 (atau /filter bid 0 untuk tanpa batas)"
            if rest.lower() in {"0", "off", "none", "reset", "semua"}:
                val = None
            else:
                try:
                    val = int(rest)
                    if val < 0:
                        raise ValueError()
                    if val == 0:
                        val = None
                except ValueError:
                    return "Jumlah bid harus berupa angka bulat positif (misal: 30) atau 0/off untuk tanpa batas."
            new_cfg = FilterConfig(
                role_keywords=cfg.role_keywords,
                exclusion_keywords=cfg.exclusion_keywords,
                min_relevance_score=cfg.min_relevance_score,
                max_posting_age_days=cfg.max_posting_age_days,
                no_response_after_days=cfg.no_response_after_days,
                max_bids=val,
            )
            repo.update(new_cfg)
            if val is None:
                return "Filter jumlah bid dinonaktifkan (semua proyek akan diambil tanpa batas bid)."
            return f"Filter max jumlah bid diubah menjadi: maksimal {val} bid per proyek."

        return "Sub-perintah filter tidak dikenal. Ketik /filter untuk lihat petunjuk."

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
        approved = self.connection.execute(
            "SELECT applications.id, jobs.title, jobs.company "
            "FROM applications JOIN jobs ON jobs.id = applications.job_id "
            "WHERE applications.status = 'APPROVED' "
            "ORDER BY applications.created_at DESC"
        ).fetchall()

        if not candidates and not pending and not approved:
            return "Belum ada lowongan kandidat atau lamaran. Ketik /fetch untuk mengambil data."

        lines = ["Lowongan & Lamaran terbaru:"]
        if candidates:
            lines.append("\n📌 CANDIDATE (Ketik /siapkan <ID>):")
            lines.extend(f"• {job_id}: {title} — {company}" for job_id, title, company in candidates)
        if pending:
            lines.append("\n⏳ PENDING_APPROVAL (Ketik /setuju <ID>):")
            lines.extend(f"• {app_id}: {title} — {company}" for app_id, title, company in pending)
        if approved:
            lines.append("\n✅ APPROVED (Siap diisi otomatis: /isi <ID>):")
            lines.extend(f"• {app_id}: {title} — {company}" for app_id, title, company in approved)

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

