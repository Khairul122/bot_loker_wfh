"""FormAgent orchestrator for BrowserMCP."""

from __future__ import annotations

import sqlite3
import time
from typing import Any
from urllib.parse import urlparse

from bot_loker_wfh.browser_mcp import McpBrowserClient
from bot_loker_wfh.form_agent.answers_v2 import AnswersStore
from bot_loker_wfh.form_agent.classifier import FieldClassifier
from bot_loker_wfh.form_agent.executor import Executor, ValueResolver
from bot_loker_wfh.form_agent.extractor import FormExtractor, FormField
from bot_loker_wfh.form_agent.planner import FormPlanner
from bot_loker_wfh.form_agent.policy import PolicyGuard
from bot_loker_wfh.form_agent.report import ReportBuilder, SessionRecordInput
from bot_loker_wfh.llm import LLMRouter


class FormAgent:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        router: LLMRouter | None = None,
        browser_command: str = "npx -y @browsermcp/mcp@0.1.3",
        min_confidence: float = 0.7,
        max_actions: int = 60,
        max_tool_calls: int = 80,
        timeout_seconds: float = 300.0,
        applicant_path: str = "data/applicant.json",
        answers_path: str = "data/answers.json",
        db_path: str | None = None,
        custom_client: Any | None = None,
    ):
        self.connection = connection
        self.router = router
        self.browser_command = browser_command
        self.min_confidence = min_confidence
        self.max_actions = max_actions
        self.max_tool_calls = max_tool_calls
        self.timeout_seconds = timeout_seconds
        self.applicant_path = applicant_path
        self.answers_path = answers_path
        self.db_path = db_path
        self.custom_client = custom_client

    def run_session(
        self,
        application_id: str,
        *,
        page_number: int = 1,
        force_assist: bool = False,
    ) -> str:
        # 1. Validasi awal
        row = self.connection.execute(
            """
            SELECT jobs.apply_url, jobs.company, jobs.title, jobs.description,
                   applications.cover_letter, applications.status
            FROM applications
            JOIN jobs ON jobs.id = applications.job_id
            WHERE applications.id = ?
            """,
            (application_id,),
        ).fetchone()
        if not row:
            return "Application tidak ditemukan."

        apply_url, company, title, description, cover_letter, app_status = row
        if app_status != "APPROVED":
            return f"Status lamaran saat ini '{app_status}', bukan 'APPROVED'."

        running_session = self.connection.execute(
            "SELECT id FROM form_sessions WHERE application_id = ? AND status = 'running'",
            (application_id,),
        ).fetchone()
        if running_session:
            return "Pengisian sebelumnya masih berjalan."

        parsed_url = urlparse(apply_url)
        host = parsed_url.hostname or ""

        # Check ats_registry
        ats_row = self.connection.execute(
            "SELECT mode, open_button_label FROM ats_registry WHERE host = ? AND active = 1",
            (host,),
        ).fetchone()

        mode = "assist"
        open_button_label = None
        if ats_row:
            mode = ats_row[0]
            open_button_label = ats_row[1]
        elif not force_assist:
            return f"Situs ini ({host}) belum terdaftar. Ketik /isi {application_id[:8]} paksa untuk mode assist."

        if force_assist:
            mode = "assist"

        # 2. Setup client
        client = self.custom_client
        if client is None:
            client = McpBrowserClient(
                command=self.browser_command,
                allowed_hosts={host} if host else set(),
                max_tool_calls=self.max_tool_calls,
                timeout=self.timeout_seconds,
            )
            try:
                client.start()
            except Exception as err:
                return (
                    f"BrowserMCP gagal start: {err}. Pastikan Node.js 18+ terpasang."
                )

        try:
            # 3. Buka halaman
            if page_number == 1:
                client.call_tool("browser_navigate", {"url": apply_url})
                time.sleep(2.0)
                if open_button_label:
                    snap = client.call_tool("browser_snapshot", {})
                    extractor = FormExtractor()
                    fields = extractor.extract(snap)
                    for f in fields:
                        if (
                            open_button_label.lower() in f.label.lower()
                            or f.role == "button"
                        ) and open_button_label.lower() in f.label.lower():
                            client.call_tool("browser_click", {"ref": f.ref})
                            time.sleep(2.0)
                            break

            # 4. Baca form
            snapshot = client.call_tool("browser_snapshot", {})
            extractor = FormExtractor()
            raw_fields = extractor.extract(snapshot)

            answers_store = AnswersStore.load(self.answers_path)
            classifier = FieldClassifier(answers_store)
            fields = classifier.classify_all(raw_fields)

            has_captcha = any(f.field_class == "captcha" for f in fields)

            # 5. Rencanakan
            planner = FormPlanner(self.router, answers_store)
            resolver = ValueResolver.from_files(
                self.applicant_path, self.answers_path, cover_letter
            )

            plan_res = planner.plan(
                fields,
                job_title=title,
                company=company,
                job_summary=description,
                candidate_summary=resolver.cover_letter,
                mode=mode,
                available_keys=resolver.get_available_keys(),
            )

            # Handle open question actions if any
            final_actions = []
            for act in plan_res.actions:
                if act.action == "answer":
                    f = next((fld for fld in fields if fld.ref == act.ref), None)
                    lbl = f.label if f else ""
                    ans_text = planner.generate_answer(
                        lbl,
                        job_summary=description,
                        candidate_summary=resolver.cover_letter,
                    )
                    final_actions.append(
                        act.__class__(
                            ref=act.ref,
                            action="answer",
                            value=ans_text,
                            source="llm",
                            confidence=act.confidence,
                        )
                    )
                else:
                    final_actions.append(act)

            # 6. Validasi rencana -> PolicyGuard
            guard = PolicyGuard(
                min_confidence=self.min_confidence,
                max_actions=self.max_actions,
                open_button_label=open_button_label,
            )
            policy_res = guard.evaluate(
                final_actions, fields, resolver.get_available_keys()
            )

            # 7. Eksekusi
            executor = Executor(client, resolver)
            events = executor.execute_plan(policy_res.approved, fields)

            # 8. Laporan & Record
            report_builder = ReportBuilder(self.db_path)
            record_input = SessionRecordInput(
                application_id=application_id,
                engine="browsermcp",
                host=host,
                mode=mode,
                page_number=page_number,
                status="filled" if not has_captcha else "captcha",
                company=company,
                job_title=title,
                all_fields=fields,
                executed_events=events,
                rejected_actions=policy_res.rejected,
                has_captcha=has_captcha,
                tool_calls=getattr(client, "tool_call_count", 0),
            )
            report_builder.record_session(record_input)
            report_text = report_builder.build_report_text(record_input)
            return report_text

        finally:
            if self.custom_client is None:
                client.stop()
