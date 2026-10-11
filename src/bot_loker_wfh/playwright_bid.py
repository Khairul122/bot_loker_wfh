"""Fill and submit an approved bid in its own browser window (Playwright, for sites without an API).

A persistent Chrome profile (`data/browser-profile`) keeps the owner's login, so signing in once
is enough. The window and tab belong to the bot: the office page is never touched and no
extension has to be connected. Fields are found by their label/placeholder, the submit button only
by an explicit "ajukan/kirim penawaran" name, and a CAPTCHA is never solved: if one shows up the
run stops with the form filled for the owner.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROFILE_DIR = Path("data/browser-profile")
LOGIN_WAIT_SECONDS = 300
KEEP_OPEN_SECONDS = 20 * 60
SUBMIT_NAME = re.compile(r"(ajukan|kirim|submit|place|send)\s*(penawaran|bid|proposal)|^\s*(ajukan|kirim)\s*$", re.I)
SUCCESS_TEXT = re.compile(r"berhasil|terkirim|telah diajukan|successfully|bid placed|penawaran (anda )?(sudah|telah)", re.I)
CAPTCHA = re.compile(r"captcha|recaptcha|hcaptcha|cf-turnstile|verifikasi bahwa anda", re.I)
LOGIN_GATE = re.compile(r"\b(login|masuk|sign in)\b.*\b(password|kata sandi)\b|silakan (login|masuk)", re.I | re.S)

# words (lower case) that identify each box
PROPOSAL = re.compile(r"proposal|deskripsi|pesan|cover|keterangan|catatan|description|message|detail")
AMOUNT = re.compile(r"harga|tawaran|penawaran|nilai|biaya|jumlah|amount|price|bid|rp")
DAYS = re.compile(r"hari|durasi|lama|pengerjaan|days|duration|delivery|waktu")
# the box's own label/placeholder/name first, then the text of the block around it
_DESCRIBE_JS = """el => [[
  (el.labels && el.labels[0] && el.labels[0].innerText) || '', el.getAttribute('aria-label') || '',
  el.placeholder || '', el.name || '', el.id || ''].join(' '),
  (el.closest('div,fieldset,td,tr,li') && el.closest('div,fieldset,td,tr,li').innerText || '').slice(0, 140)]"""


@dataclass
class BidResult:
    status: str   # submitted | submitted_unverified | filled_only | login_timeout | captcha | missing_fields | no_submit_button
    message: str

    @property
    def submitted(self) -> bool:
        return self.status == "submitted"


def match_fields(items: list[tuple[int, str, str, str]]) -> dict[str, int]:
    """Pick one control per field from (index, tag, own_text, block_text). A textarea is the proposal."""
    chosen: dict[str, int] = {}

    def best(pattern, pool):
        for field in (2, 3):  # own label first, surrounding block only as a fallback
            hit = [c for c in pool if pattern.search(c[field])]
            if hit:
                return hit
        return []

    areas = [c for c in items if c[1] == "textarea"]
    inputs = [c for c in items if c[1] != "textarea"]
    proposal = best(PROPOSAL, areas) or areas
    if proposal:
        chosen["proposal"] = proposal[0][0]
    days = best(DAYS, inputs)
    amount = [c for c in best(AMOUNT, inputs) if not DAYS.search(c[2])] or best(AMOUNT, inputs)
    if amount:
        chosen["amount"] = amount[0][0]
    days = [c for c in days if c[0] != chosen.get("amount")]
    if days:
        chosen["days"] = days[0][0]
    return chosen


def _controls(page: Any):
    locator = page.locator("input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=file]):not([type=submit]):not([type=button]), textarea")
    items = []
    for i in range(locator.count()):
        element = locator.nth(i)
        try:
            if not element.is_visible():
                continue
            tag = element.evaluate("el => el.tagName.toLowerCase()")
            own, block = element.evaluate(_DESCRIBE_JS)
            items.append((i, tag, own.lower(), block.lower()))
        except Exception:
            continue
    return locator, items


def _submit_button(page: Any):
    for role in ("button", "link"):
        button = page.get_by_role(role, name=SUBMIT_NAME)
        if button.count():
            return button.first
    inputs = page.locator("input[type=submit]")
    for i in range(inputs.count()):
        if SUBMIT_NAME.search(inputs.nth(i).get_attribute("value") or ""):
            return inputs.nth(i)
    return None


def _fill_and_submit(page: Any, *, amount: str, days: str, proposal: str, login_wait: float, sleep=time.sleep) -> BidResult:
    deadline = time.time() + login_wait
    while True:
        locator, items = _controls(page)
        found = match_fields(items)
        if "amount" in found and "proposal" in found:
            break
        if CAPTCHA.search(page.content()):
            return BidResult("captcha", "Ada CAPTCHA: selesaikan sendiri di jendela yang terbuka.")
        if time.time() >= deadline:
            gate = LOGIN_GATE.search(page.inner_text("body") or "")
            return BidResult("login_timeout" if gate else "missing_fields",
                             "Belum login di jendela bot; login lalu setujui lagi." if gate else
                             "Kolom harga/proposal tidak ditemukan di halaman ini; isi manual di jendela yang terbuka.")
        sleep(3)
    if CAPTCHA.search(page.content()):
        return BidResult("captcha", "Ada CAPTCHA: selesaikan sendiri di jendela yang terbuka.")
    values = {"proposal": proposal, "amount": amount, "days": days}
    for key, index in found.items():
        if values[key]:
            locator.nth(index).fill(values[key])
    button = _submit_button(page)
    if button is None:
        return BidResult("no_submit_button", "Form terisi tetapi tombol 'Ajukan Penawaran' tidak ditemukan; kirim manual.")
    button.click()
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    body = page.inner_text("body") or ""
    if SUCCESS_TEXT.search(body) or _submit_button(page) is None:
        return BidResult("submitted", "Bid terkirim.")
    return BidResult("submitted_unverified", "Tombol sudah diklik tetapi hasilnya belum terverifikasi; cek halaman proyek.")


def submit_bid(url: str, *, amount: str, days: str, proposal: str, profile_dir: Path = PROFILE_DIR,
               login_wait: float = LOGIN_WAIT_SECONDS, headless: bool = False, playwright_factory=None) -> BidResult:
    """Open the project in the bot's own window, fill the approved bid and press the submit button."""
    if playwright_factory is None:
        try:
            from playwright.sync_api import sync_playwright as playwright_factory
        except ImportError:
            return BidResult("missing_fields", "Playwright belum terpasang: pip install playwright && python -m playwright install chromium")
    profile_dir.mkdir(parents=True, exist_ok=True)
    with playwright_factory() as playwright:
        try:
            context = playwright.chromium.launch_persistent_context(
                str(profile_dir), channel="chrome", headless=headless, viewport={"width": 1280, "height": 900})
        except Exception:
            try:
                context = playwright.chromium.launch_persistent_context(str(profile_dir), headless=headless)
            except Exception:
                return BidResult("missing_fields", "Browser tidak bisa dibuka (tutup Chrome yang memakai profil data/browser-profile).")
        try:
            page = context.new_page()  # its own tab in the bot's own window
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)
            result = _fill_and_submit(page, amount=amount, days=days, proposal=proposal, login_wait=login_wait)
            if not result.submitted:  # leave the window open so the owner can finish by hand
                try:
                    page.wait_for_event("close", timeout=KEEP_OPEN_SECONDS * 1000)
                except Exception:
                    pass
            return result
        finally:
            context.close()
