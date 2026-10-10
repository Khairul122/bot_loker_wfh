"""Form filling helpers: target resolution, applicant data and the fill-process launchers.

The browser work itself lives in `form_agent` (BrowserMCP). Job applications stop before
Submit; a freelance bid is submitted only after the owner approved it in the office web UI.
CAPTCHA is never solved or bypassed.
"""

from __future__ import annotations

import json
import os
import re
from .database import Connection
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


GREENHOUSE_HOSTS = frozenset({"job-boards.greenhouse.io", "boards.greenhouse.io"})
LEVER_HOSTS = frozenset({"jobs.lever.co", "jobs.eu.lever.co"})


def spawn_fill_form(
    application_id: str,
    *,
    spawn: Callable[..., Any] = subprocess.Popen,
    force_assist: bool = False,
    next_page: bool = False,
) -> Any:
    """Start the form filler as a separate process; output goes to data/logs/fill-form.log.

    Returns the running process so the caller can watch it finish.
    """
    cmd = [sys.executable, "-m", "bot_loker_wfh", "fill-form", "--application-id", application_id]
    if force_assist:
        cmd.append("--force-assist")
    if next_page:
        cmd.append("--next-page")
    log_dir = Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    # the child gets its own copy of the handle, so the parent can close it right away
    with (log_dir / "fill-form.log").open("a", encoding="utf-8") as log_file:
        return spawn(cmd, cwd=os.getcwd(), stdout=log_file, stderr=log_file)


def spawn_fill_lead(
    lead_id: str, *, submit: bool = False, spawn: Callable[..., Any] = subprocess.Popen
) -> Any:
    """Start the bid-form filler for a freelance lead; output goes to data/logs/fill-lead.log.

    `submit=True` is only for a bid the owner explicitly approved in the web UI.
    """
    cmd = [sys.executable, "-m", "bot_loker_wfh", "fill-lead", "--lead-id", lead_id]
    if submit:
        cmd += ["--submit-bid", "--approved"]
    log_dir = Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    # the child gets its own copy of the handle, so the parent can close it right away
    with (log_dir / "fill-lead.log").open("a", encoding="utf-8") as log_file:
        return spawn(cmd, cwd=os.getcwd(), stdout=log_file, stderr=log_file)


class FormAssistError(RuntimeError):
    """The form cannot be prepared automatically; the message is user-safe."""


@dataclass(frozen=True)
class Applicant:
    first_name: str
    last_name: str
    email: str
    phone: str = ""
    resume_path: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()




def load_applicant(path: str | Path) -> Applicant:
    applicant_path = Path(path)
    if not applicant_path.is_file():
        raise FormAssistError(
            f"File data pelamar tidak ada: {applicant_path}. "
            "Salin resume/applicant.example.json ke sana dan isi."
        )
    data = json.loads(applicant_path.read_text(encoding="utf-8-sig"))
    applicant = Applicant(
        first_name=str(data.get("first_name", "")).strip(),
        last_name=str(data.get("last_name", "")).strip(),
        email=str(data.get("email", "")).strip(),
        phone=str(data.get("phone", "")).strip(),
        resume_path=str(data.get("resume_path", "")).strip(),
        linkedin=str(data.get("linkedin", "")).strip(),
        github=str(data.get("github", "")).strip(),
        website=str(data.get("website", "")).strip(),
    )
    if not (applicant.first_name and applicant.last_name and applicant.email):
        raise FormAssistError("first_name, last_name, dan email wajib diisi di data pelamar.")
    return applicant


def load_answers(path: str | Path) -> dict[str, str]:
    answers_path = Path(path)
    if not answers_path.is_file():
        return {}
    data = json.loads(answers_path.read_text(encoding="utf-8-sig"))
    return {str(key): str(value) for key, value in data.items() if str(value).strip()}


def ats_for_url(url: str, connection: Connection | None = None) -> str | None:
    """Return the ATS name for allowlisted hosts or ats_registry entries."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return None
    if parsed.hostname in GREENHOUSE_HOSTS:
        return "greenhouse"
    if parsed.hostname in LEVER_HOSTS:
        return "lever"
    if connection is not None and parsed.hostname:
        row = connection.execute(
            "SELECT ats_name FROM ats_registry WHERE host = ? AND active = 1",
            (parsed.hostname,),
        ).fetchone()
        if row is not None:
            return str(row[0]).lower()
    return None


def resolve_form_target(
    connection: Connection, application_id: str
) -> tuple[str, str, str, str]:
    """Return (ats, form_url, cover_letter, job_title) for an application."""
    row = connection.execute(
        "SELECT jobs.source, jobs.external_id, jobs.apply_url, jobs.company, jobs.title, "
        "applications.cover_letter FROM applications "
        "JOIN jobs ON jobs.id = applications.job_id WHERE applications.id = ?",
        (application_id,),
    ).fetchone()
    if row is None:
        raise FormAssistError("Application tidak ditemukan.")
    source, external_id, apply_url, company, title, cover_letter = row

    if source == "greenhouse":
        slug_row = connection.execute(
            "SELECT ats_slug FROM companies_ats WHERE ats_type = 'greenhouse' "
            "AND company_name = ? LIMIT 1",
            (company,),
        ).fetchone()
        if slug_row is not None:
            url = f"https://job-boards.greenhouse.io/{slug_row[0]}/jobs/{external_id}"
            return "greenhouse", url, cover_letter, title
    ats = ats_for_url(apply_url, connection=connection)
    if ats is None:
        raise FormAssistError(
            "Situs lamaran ini belum didukung untuk pengisian otomatis. "
            f"Buka manual: {apply_url}"
        )
    return ats, apply_url, cover_letter, title
