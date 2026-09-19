"""Semi-automatic application form filling (Greenhouse and Lever).

The assistant opens the real application form in a visible browser, fills the
fields it can map safely, and then STOPS. It never clicks the submit button,
never solves or bypasses CAPTCHA, and never guesses answers to questions it
does not have a reviewed answer for: the user reviews the form and submits it.
"""

from __future__ import annotations

import json
import re
import sqlite3
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


GREENHOUSE_HOSTS = frozenset({"job-boards.greenhouse.io", "boards.greenhouse.io"})
LEVER_HOSTS = frozenset({"jobs.lever.co", "jobs.eu.lever.co"})
LEVER_RESUME_PARSE_SECONDS = 4


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


@dataclass
class FillReport:
    ats: str
    filled: list[str] = field(default_factory=list)
    needs_manual: list[str] = field(default_factory=list)
    captcha: bool = False

    def to_text(self) -> str:
        lines = ["Form sudah dibuka di browser Anda dan TIDAK dikirim."]
        lines.append("Terisi: " + (", ".join(self.filled) or "-"))
        if self.needs_manual:
            lines.append("Perlu Anda isi/pilih: " + "; ".join(self.needs_manual))
        if self.captcha:
            lines.append("Ada CAPTCHA: selesaikan sendiri.")
        lines.append(
            "Periksa semuanya, tekan Submit sendiri, lalu ketik /dilamar <id> di sini."
        )
        return "\n".join(lines)


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


def ats_for_url(url: str) -> str | None:
    """Return the ATS name only for exact allowlisted https hosts."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return None
    if parsed.hostname in GREENHOUSE_HOSTS:
        return "greenhouse"
    if parsed.hostname in LEVER_HOSTS:
        return "lever"
    return None


def resolve_form_target(
    connection: sqlite3.Connection, application_id: str
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
    ats = ats_for_url(apply_url)
    if ats is None:
        raise FormAssistError(
            "Situs lamaran ini belum didukung untuk pengisian otomatis. "
            f"Buka manual: {apply_url}"
        )
    return ats, apply_url, cover_letter, title


_UNFILLED_REQUIRED_JS = """
() => {
  const labelOf = (e) => {
    const own = e.labels && e.labels[0] ? e.labels[0].innerText : '';
    const near = e.closest('li, .field, .application-question, .select__container, div')
      ?.querySelector('.application-label, label')?.innerText || '';
    return (own || e.getAttribute('aria-label') || near || '').replace(/[*✱]/g, '').trim();
  };
  const seen = new Set();
  return [...document.querySelectorAll('input, textarea, select')]
    .filter((e) => e.type !== 'hidden' && e.type !== 'search' && e.offsetParent !== null)
    .filter((e) => e.required || e.getAttribute('aria-required') === 'true')
    .filter((e) => e.type === 'file' ? e.files.length === 0 : (e.value || '').trim() === '')
    .map(labelOf)
    .filter((label) => label && !seen.has(label) && seen.add(label))
    .map((label) => label.replace(/\\s+/g, ' ').slice(0, 80));
}
"""


def fill_page(
    page: Any,
    ats: str,
    applicant: Applicant,
    cover_letter: str,
    answers: dict[str, str] | None = None,
) -> FillReport:
    """Fill a loaded application page. Never submits."""
    report = FillReport(ats=ats)
    if ats == "greenhouse":
        _fill_greenhouse(page, applicant, cover_letter, report)
    elif ats == "lever":
        _fill_lever(page, applicant, cover_letter, report)
    else:
        raise FormAssistError("ATS tidak didukung.")

    for label, value in (answers or {}).items():
        _fill_custom(page, label, value, report)

    report.captcha = any(
        "hcaptcha" in frame.url or "recaptcha" in frame.url for frame in page.frames
    )
    filled_labels = {name.lower() for name in report.filled}
    for label in page.evaluate(_UNFILLED_REQUIRED_JS):
        if label.lower() not in filled_labels:
            report.needs_manual.append(label)
    return report


def _fill_greenhouse(
    page: Any, applicant: Applicant, cover_letter: str, report: FillReport
) -> None:
    _fill(page, "#first_name", applicant.first_name, "First Name", report)
    _fill(page, "#last_name", applicant.last_name, "Last Name", report)
    _fill(page, "#email", applicant.email, "Email", report)
    _fill(page, "#phone", applicant.phone, "Phone", report)
    _upload(page, "input#resume", applicant.resume_path, "Resume", report)
    _cover_letter(page, "#cover_letter", cover_letter, report)
    for label, value in (
        ("LinkedIn", applicant.linkedin),
        ("GitHub", applicant.github),
        ("Website", applicant.website),
    ):
        _fill_custom(page, label, value, report)


def _fill_lever(
    page: Any, applicant: Applicant, cover_letter: str, report: FillReport
) -> None:
    # Uploading the resume triggers Lever's parser, which can overwrite other
    # fields, so upload first and fill the fields afterwards.
    if _upload(page, "input[name='resume']", applicant.resume_path, "Resume", report):
        time.sleep(LEVER_RESUME_PARSE_SECONDS)
    _fill(page, "input[name='name']", applicant.full_name, "Full name", report)
    _fill(page, "input[name='email']", applicant.email, "Email", report)
    _fill(page, "input[name='phone']", applicant.phone, "Phone", report)
    _fill(page, "input[name='urls[LinkedIn]']", applicant.linkedin, "LinkedIn", report)
    _fill(page, "input[name='urls[GitHub]']", applicant.github, "GitHub", report)
    _fill(page, "input[name='urls[Other]']", applicant.website, "Website", report)
    _fill(page, "textarea[name='comments']", cover_letter, "Additional information", report)


def _fill(page: Any, selector: str, value: str, name: str, report: FillReport) -> bool:
    if not value.strip():
        return False
    locator = page.locator(selector)
    if locator.count() != 1:
        return False
    locator.fill(value)
    report.filled.append(name)
    return True


def _upload(page: Any, selector: str, path: str, name: str, report: FillReport) -> bool:
    if not path.strip() or not Path(path).is_file():
        return False
    locator = page.locator(selector)
    if locator.count() != 1:
        return False
    locator.set_input_files(path)
    report.filled.append(name)
    return True


def _cover_letter(page: Any, selector: str, text: str, report: FillReport) -> None:
    locator = page.locator(selector)
    if locator.count() != 1 or not text.strip():
        return
    if locator.evaluate("(e) => e.type") == "file":
        with tempfile.TemporaryDirectory() as directory:
            letter = Path(directory) / "cover_letter.txt"
            letter.write_text(text, encoding="utf-8")
            locator.set_input_files(str(letter))
    else:
        locator.fill(text)
    report.filled.append("Cover letter")


def _fill_custom(page: Any, label: str, value: str, report: FillReport) -> None:
    """Fill a text-like field found by label, only when exactly one field matches."""
    if not value.strip():
        return
    locator = page.get_by_label(re.compile(re.escape(label), re.IGNORECASE))
    if locator.count() != 1:
        return
    kind = locator.evaluate(
        "(e) => e.tagName === 'TEXTAREA' ? 'text' : (e.tagName === 'INPUT' && "
        "e.getAttribute('role') !== 'combobox' && !['file','checkbox','radio']"
        ".includes(e.type)) ? 'text' : 'other'"
    )
    if kind != "text":
        return
    locator.fill(value)
    report.filled.append(label)


def open_and_fill(
    connection: sqlite3.Connection,
    application_id: str,
    applicant: Applicant,
    answers: dict[str, str],
    *,
    on_ready: Callable[[FillReport], None] | None = None,
) -> FillReport:
    """Open the form in a visible browser, fill it, and leave it open for the user."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise FormAssistError(
            "Playwright belum terpasang: pip install playwright && "
            "python -m playwright install chromium"
        ) from error

    ats, url, cover_letter, _title = resolve_form_target(connection, application_id)
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=False)
        except Exception as error:
            raise FormAssistError(
                "Browser tidak bisa dibuka (perlu layar/desktop, dan "
                "`python -m playwright install chromium`)."
            ) from error
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        report = fill_page(page, ats, applicant, cover_letter, answers)
        if on_ready is not None:
            on_ready(report)
            # Keep the browser open until the user closes the page.
            try:
                page.wait_for_event("close", timeout=0)
            except Exception:
                pass
        browser.close()
    return report
