"""FormAgent orchestrator for BrowserMCP."""

from __future__ import annotations

from ..database import Connection
import time
import re
from typing import Any
from urllib.parse import urlparse

# A visible "Log In" / "Masuk" link means the bid form is hidden behind a login.
LOGIN_GATE = re.compile(r'(link|button) "(log ?in|sign in|masuk)"', re.IGNORECASE)
LOGIN_WAIT_SECONDS = 10 * 60
RENDER_WAIT_SECONDS = 25.0  # SPA pages (Freelancer) render long after navigate returns

from bot_loker_wfh.browser_mcp import McpBrowserClient, McpNotConnectedError
from bot_loker_wfh.cv_profile import load_profile
from bot_loker_wfh.form_agent.answers_v2 import AnswersStore
from bot_loker_wfh.form_agent.bid_terms import choose_bid_terms
from bot_loker_wfh.lead_desk import get_bid_terms, submit_allowed
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
        connection: Connection,
        *,
        router: LLMRouter | None = None,
        browser_command: str = "npx -y @browsermcp/mcp@0.1.3",
        min_confidence: float = 0.7,
        max_actions: int = 60,
        max_tool_calls: int = 80,
        timeout_seconds: float = 300.0,
        connect_timeout_seconds: float = 20.0,
        applicant_path: str = "data/applicant.json",
        answers_path: str = "data/answers.json",
        profile_path: str = "data/profile.json",
        persist_reports: bool = False,
        custom_client: Any | None = None,
        ai_answers: bool = True,
    ):
        self.connection = connection
        self.router = router
        self.browser_command = browser_command
        self.min_confidence = min_confidence
        self.max_actions = max_actions
        self.max_tool_calls = max_tool_calls
        self.timeout_seconds = timeout_seconds
        self.connect_timeout_seconds = connect_timeout_seconds
        self.applicant_path = applicant_path
        self.answers_path = answers_path
        self.profile_path = profile_path
        self.persist_reports = persist_reports
        self.custom_client = custom_client
        self.ai_answers = ai_answers

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

        return self._session(
            apply_url=apply_url,
            company=company,
            title=title,
            description=description,
            cover_letter=cover_letter,
            record_id=application_id,
            page_number=page_number,
            force_assist=force_assist,
        )

    def run_lead_session(
        self,
        lead_id: str,
        *,
        keep_open_seconds: float = 0,
        text: str = "proposal",
        submit: bool = False,
        confirm_submit: Any = None,
        require_approved: bool = False,
    ) -> str:
        """Fill the bid form; submit only after the owner's confirmation.

        `require_approved` is the web flow: the owner pressed "Setujui & Kirim", so the lead is
        APPROVED in the database. A failed or unfinished run puts it back to INTERESTED.
        """
        if text not in ("proposal", "comment"):
            raise ValueError("text must be proposal or comment")
        row = self.connection.execute(
            f"SELECT url, source, title, description, budget, {text}, status FROM leads WHERE id = ?",
            (lead_id,),
        ).fetchone()
        if not row:
            return "Proyek tidak ditemukan."
        url, source, title, description, budget, proposal, lead_status = row
        if submit and lead_status == "SUBMITTED":
            return "Bid sudah berstatus SUBMITTED; pengiriman ulang diblokir."
        if submit and require_approved and lead_status != "APPROVED":
            return "Bid belum disetujui owner; pengiriman diblokir."
        if submit and not submit_allowed(url):
            return "Pengiriman otomatis hanya untuk Freelancer.com dan Projects.co.id."
        if not (proposal or "").strip():
            return f"Tulis {text} dulu (draft-lead) sebelum mengisi formulir."
        if text == "proposal" and len(proposal.strip()) < 100:
            return "Proposal minimal 100 karakter untuk mengajukan penawaran."
        bid_terms = get_bid_terms(self.connection, lead_id) or choose_bid_terms(
            self.router, title=title, description=description, budget=budget
        )
        try:
            return self._run_lead(
                url, source, title, description, proposal, bid_terms, lead_id,
                keep_open_seconds, submit, confirm_submit,
            )
        finally:
            if submit:  # anything but a confirmed SUBMITTED leaves the owner's approval open again
                self.connection.execute(
                    "UPDATE leads SET status = 'INTERESTED' WHERE id = ? AND status = 'APPROVED'", (lead_id,)
                )
                self.connection.commit()

    def _run_lead(
        self, url, source, title, description, proposal, bid_terms, lead_id,
        keep_open_seconds, submit, confirm_submit,
    ) -> str:
        return self._session(
            apply_url=url,
            company=source,
            title=title,
            description=description,
            cover_letter=proposal,
            bid_data=bid_terms.as_values() if bid_terms else {},
            record_id=None,  # form_sessions belongs to job applications
            lead_id=lead_id,
            page_number=1,
            force_assist=True,  # bid pages are not in the ATS registry
            keep_open_seconds=keep_open_seconds,
            submit=submit,
            confirm_submit=confirm_submit,
        )

    @staticmethod
    def _wait_for_render(client: Any, max_seconds: float = RENDER_WAIT_SECONDS) -> None:
        """Poll until the page snapshot has real content, not just an empty document."""
        if not hasattr(client, "peek_snapshot"):
            time.sleep(2.0)
            return
        # Done when the element count stops growing: late widgets (the bid box) attach last.
        deadline = time.time() + max_seconds
        previous = -1
        while time.time() < deadline:
            time.sleep(2.0)
            count = (client.peek_snapshot() or "").count("[ref=")
            if count >= 30 and count == previous:
                return
            previous = count

    @staticmethod
    def _wait_for_login(client: Any, max_seconds: float, poll_seconds: float = 5.0) -> bool:
        deadline = time.time() + max_seconds
        while time.time() < deadline:
            time.sleep(poll_seconds)
            text = client.peek_snapshot()
            if text is None:
                return False  # browser was closed
            if not LOGIN_GATE.search(text) and "login" not in text.lower().split("page url:")[-1][:80]:
                return True
        return False

    def _session(
        self,
        *,
        apply_url: str,
        company: str,
        title: str,
        description: str,
        cover_letter: str,
        record_id: str | None,
        page_number: int,
        force_assist: bool,
        keep_open_seconds: float = 0,
        bid_data: dict[str, str] | None = None,
        lead_id: str | None = None,
        submit: bool = False,
        confirm_submit: Any = None,
    ) -> str:
        application_id = record_id or ""
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
            # Tunggu ekstensi terhubung
            if hasattr(client, "wait_for_extension"):
                try:
                    client.wait_for_extension(self.connect_timeout_seconds)
                except McpNotConnectedError:
                    return (
                        "Ekstensi BrowserMCP belum terhubung. "
                        "Buka Chrome, klik ikon BrowserMCP, tekan Connect, lalu ulangi /isi."
                    )

            # 3. Buka halaman
            if page_number == 1:
                client.call_tool("browser_navigate", {"url": apply_url})
                self._wait_for_render(client)
                if open_button_label:
                    snap = client.call_tool("browser_snapshot", {})
                    extractor = FormExtractor()
                    fields = extractor.extract(snap)
                    for f in fields:
                        if (
                            open_button_label.lower() in f.label.lower()
                            or f.role == "button"
                        ) and open_button_label.lower() in f.label.lower():
                            client.call_tool(
                                "browser_click",
                                {"element": open_button_label, "ref": f.ref},
                            )
                            time.sleep(2.0)
                            break

            # Bid pages hide the form until the owner is logged in: wait for them in
            # this same window (it stays open), then reload the project page.
            if keep_open_seconds and hasattr(client, "peek_snapshot"):
                if LOGIN_GATE.search(client.peek_snapshot() or ""):
                    print("Belum login. Silakan login di jendela browser yang terbuka; "
                          "form akan diisi otomatis setelah kamu login.", flush=True)
                    if not self._wait_for_login(client, LOGIN_WAIT_SECONDS):
                        return "Login tidak terdeteksi dalam 10 menit. Form tidak diisi."
                    client.call_tool("browser_navigate", {"url": apply_url})
                    self._wait_for_render(client)

            # 4. Baca form
            snapshot = client.call_tool("browser_snapshot", {})
            extractor = FormExtractor()
            raw_fields = extractor.extract(snapshot)

            answers_store = AnswersStore.load(self.answers_path)
            classifier = FieldClassifier(answers_store)
            fields = classifier.classify_all(raw_fields)

            has_captcha = any(f.field_class == "captcha" for f in fields)

            # 5. Rencanakan
            planner = FormPlanner(self.router, answers_store, ai_answers=self.ai_answers)
            resolver = ValueResolver.from_files(
                self.applicant_path, self.answers_path, cover_letter
            )
            if bid_data:
                resolver.bid_data = bid_data

            candidate_summary = ""
            try:
                candidate_summary = load_profile(self.profile_path).to_summary()
            except Exception:
                candidate_summary = ""

            plan_res = planner.plan(
                fields,
                job_title=title,
                company=company,
                job_summary=description,
                candidate_summary=candidate_summary,
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
                        candidate_summary=candidate_summary,
                    )
                    # No usable answer (AI off or refused): leave the field for the owner
                    # instead of typing the placeholder text into it.
                    if not ans_text or ans_text == "NEEDS_USER":
                        continue
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

            submit_status = "not_requested"
            if submit:
                if has_captcha:
                    submit_status = "blocked_captcha"
                else:
                    final_snapshot = client.call_tool("browser_snapshot", {})
                    final_fields = classifier.classify_all(
                        FormExtractor().extract(final_snapshot)
                    )
                    final_has_captcha = any(
                        field.field_class == "captcha" for field in final_fields
                    )
                    submit_field = next(
                        (
                            field
                            for field in final_fields
                            if field.role == "button"
                            and re.search(
                                r"^(submit|submit bid|ajukan penawaran|kirim penawaran|place bid)$",
                                (field.label or "").strip(),
                                re.IGNORECASE,
                            )
                        ),
                        None,
                    )
                    execution_failed = any(
                        event.action in {"error", "failed", "verify_failed"}
                        for event in events
                    )
                    required_missing = any(
                        field.required
                        and field.role not in {"button", "link"}
                        and not field.current_value.strip()
                        and not any(
                            event.ref == field.ref
                            and event.action in {"filled", "ai_answered"}
                            for event in events
                        )
                        for field in final_fields
                    )
                    if final_has_captcha:
                        submit_status = "blocked_captcha"
                    elif execution_failed or required_missing:
                        submit_status = "blocked_incomplete_form"
                    elif not submit_field:
                        submit_status = "submit_button_not_found"
                    elif confirm_submit is None or not confirm_submit(submit_field.label):
                        submit_status = "not_confirmed"
                    else:
                        client.call_tool(
                            "browser_click",
                            {"element": submit_field.label, "ref": submit_field.ref},
                        )
                        time.sleep(2.0)
                        after_submit = client.call_tool("browser_snapshot", {})
                        after_fields = FormExtractor().extract(after_submit)
                        success_labels = {
                            (field.label or "").strip().lower()
                            for field in after_fields
                            if field.role in {"heading", "alert", "status"}
                        }
                        submit_status = (
                            "submitted"
                            if success_labels.intersection(
                                {"success", "berhasil", "bid submitted", "penawaran berhasil dikirim"}
                            )
                            else "submit_clicked_unverified"
                        )
                        if submit_status == "submitted" and lead_id:
                            self.connection.execute(
                                "UPDATE leads SET status = 'SUBMITTED' WHERE id = ? AND status != 'SUBMITTED'",
                                (lead_id,),
                            )
                            self.connection.commit()

            # 8. Laporan & Record
            report_builder = ReportBuilder(self.persist_reports)
            record_input = SessionRecordInput(
                application_id=application_id,
                engine="browsermcp",
                host=host,
                mode=mode,
                page_number=page_number,
                status=(
                    "filled" if not has_captcha and submit_status == "not_requested" else
                    "captcha" if has_captcha else
                    submit_status
                ),
                company=company,
                job_title=title,
                all_fields=fields,
                executed_events=events,
                rejected_actions=policy_res.rejected,
                has_captcha=has_captcha,
                tool_calls=getattr(client, "tool_call_count", 0),
            )
            if record_id:
                report_builder.record_session(record_input)
            report_text = report_builder.build_report_text(record_input)
            if keep_open_seconds and hasattr(client, "hold_open"):
                print(report_text, flush=True)
                client.hold_open(keep_open_seconds)
            return report_text

        finally:
            if self.custom_client is None:
                client.stop()
