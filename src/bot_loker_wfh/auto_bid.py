"""Hands-off freelance bidding: Cora's drafts that pass the guard rails are sent through the Freelancer API.

Everything is bounded by settings the owner controls (all stored in Supabase `app_settings`):
  auto_bid_enabled        "1" turns it on (default off)
  auto_bid_max_per_day    bids sent in any rolling 24 hours
  auto_bid_min_score      minimum relevance score of the project
  auto_bid_max_competitors  skip projects that already have more bids than this
  auto_bid_max_age_hours  only fresh projects (an early bid wins)
Only Freelancer.com (official API) is automatic. Bids use the saved proposal and terms, and each
lead is atomically claimed before submission. A failed lead is not retried automatically; repeated
refusals are bounded, and account/token failures switch auto-bid off and alert the owner.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .database import Connection
from .form_agent.bid_terms import parse_budget
from .freelancer_api import FreelancerError
from .lead_desk import WHEN, LeadClaimLost, approve_lead, get_bid_terms
from .settings_store import get_setting, set_setting

# only account-wide trouble switches auto-bid off; a refusal about one project (needs verification,
# already closed, ...) just skips that project
FATAL = ("token", "kedaluwarsa", "insufficient", "quota", "suspend")
MAX_FAILURES_PER_PASS = 3
# Freelancer only lets verified accounts bid on projects of USD 2,500 and over
UNVERIFIED_BUDGET_CAP = 2500
DOLLAR_LIKE = {"USD", "EUR", "GBP", "AUD", "CAD", "NZD", "SGD", "CHF"}
AUTO_BID_KEYS = ("auto_bid_enabled", "auto_bid_max_per_day", "auto_bid_min_score", "auto_bid_max_competitors", "auto_bid_max_age_hours")


def config(connection: Connection) -> dict[str, float]:
    return {
        "enabled": get_setting(connection, "auto_bid_enabled") == "1",
        "per_day": int(float(get_setting(connection, "auto_bid_max_per_day"))),
        "min_score": float(get_setting(connection, "auto_bid_min_score")),
        "max_competitors": int(float(get_setting(connection, "auto_bid_max_competitors"))),
        "max_age_hours": float(get_setting(connection, "auto_bid_max_age_hours")),
    }


def bid_detail(connection: Connection, lead_id: str) -> str:
    """Project, full price terms and Cora's complete draft for a Telegram bid report (owner's chat only).

    Never includes the token. Telegram caps messages, so the sender splits long text (see split_text).
    """
    row = connection.execute(
        "SELECT title, source, budget, url, score, proposal FROM leads WHERE id = ?", (lead_id,)
    ).fetchone()
    if row is None:
        return ""
    title, source, budget, url, score, proposal = row
    parsed = parse_budget(budget)
    currency = f"{parsed.currency} " if parsed and parsed.currency else ""
    terms = get_bid_terms(connection, lead_id)
    lines = [f"Proyek: {title}", f"Sumber: {source}", f"Budget klien: {budget or '-'}"]
    if terms and (terms.amount or terms.hourly_rate):
        if parsed and parsed.hourly:
            lines.append(f"Tarif bid: {currency}{terms.hourly_rate or terms.amount}/jam, maks {terms.weekly_limit or '-'} jam/minggu")
        else:
            lines.append(f"Harga bid: {currency}{terms.amount or terms.hourly_rate}")
        lines.append(f"Durasi: {terms.duration_days or '-'} hari")
        if terms.milestones:
            lines.append(f"Milestone: {terms.milestones}")
    else:
        lines.append("Harga bid: belum diisi")
    lines.append(f"Skor: {score}")
    lines.append(f"Link: {url}")
    lines.append("")
    lines.append("📝 Draft Cora:")
    lines.append((proposal or "").strip() or "(draf kosong)")
    return "\n".join(lines)


def split_text(text: str, limit: int = 3900) -> list[str]:
    """Cut at line breaks (hard cut only for one huge line) so no draft is silently truncated by Telegram."""
    parts: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        cut = cut if cut > limit // 2 else limit
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip("\n")
    return [*parts, text]


def bid_success_text(connection: Connection, lead_id: str, *, auto: bool) -> str:
    return f"✅ Bid {'otomatis ' if auto else ''}BERHASIL terkirim\n{bid_detail(connection, lead_id)}"


def bid_failure_text(connection: Connection, lead_id: str, reason: str, tail: str = "") -> str:
    return f"❌ Bid GAGAL\n{bid_detail(connection, lead_id)}\nAlasan: {reason}" + (f"\n{tail}" if tail else "")


def sent_last_24h(connection: Connection) -> int:
    return connection.execute(
        "SELECT COUNT(*) FROM leads WHERE bid_auto = 1 AND bid_submitted_at >= utc_now_iso('-24 hours')"
    ).fetchone()[0]


def candidates(connection: Connection, cfg: dict, limit: int) -> list[tuple[str, str]]:
    """Fresh, relevant, drafted, not-yet-bid Freelancer projects, best first: [(id, title)]."""
    rows = connection.execute(
        "SELECT id, title, budget FROM leads WHERE source = 'freelancer' AND status IN ('NEW', 'INTERESTED') "
        "AND length(COALESCE(proposal, '')) >= 100 AND bid_error IS NULL AND bid_submitted_at IS NULL "
        f"AND score >= ? AND {WHEN} >= now() - (? * interval '1 hour') "
        f"ORDER BY score DESC, {WHEN} DESC LIMIT 60",
        (cfg["min_score"], cfg["max_age_hours"]),
    ).fetchall()
    picked = []
    for lead_id, title, budget in rows:
        parsed = parse_budget(budget)
        if parsed is None or parsed.hourly:  # no readable budget = no defensible price; hourly bids are manual
            continue
        if parsed.currency in DOLLAR_LIKE and max(parsed.low, parsed.high or 0) >= UNVERIFIED_BUDGET_CAP:
            continue  # the platform refuses unverified accounts on big projects
        if parsed.bids is not None and parsed.bids > cfg["max_competitors"]:
            continue
        picked.append((lead_id, title))
        if len(picked) >= limit:
            break
    return picked


def run_auto_bids(
    connection: Connection, place: Callable[[Connection, str], Any] | None, notify: Callable[[str], None] | None = None,
    reconcile: Callable[[Connection], int] | None = None,
) -> dict[str, Any]:
    """Send eligible Freelancer drafts while auto-bid is enabled and within its daily cap."""
    cfg = config(connection)
    if not cfg["enabled"]:
        return {"sent": 0, "skipped": "disabled"}
    if place is None:
        return {"sent": 0, "skipped": "freelancer_api_not_configured"}

    try:
        reconciled = reconcile(connection) if reconcile is not None else 0
    except Exception:
        return {"sent": 0, "skipped": "reconciliation_failed"}

    remaining = max(0, int(cfg["per_day"]) - sent_last_24h(connection))
    if not remaining:
        return {"sent": 0, "skipped": "daily_limit", "reconciled": reconciled}
    selected = candidates(connection, cfg, remaining)
    if not selected:
        return {"sent": 0, "skipped": "no_candidates", "reconciled": reconciled}

    sent = 0
    already_sent = 0
    failures = 0
    for lead_id, _title in selected:
        # Respect a concurrent owner pause and the rolling cap between submissions.
        cfg = config(connection)
        if not cfg["enabled"]:
            return {"sent": sent, "skipped": "disabled_during_run", "reconciled": reconciled}
        if sent_last_24h(connection) >= int(cfg["per_day"]):
            return {"sent": sent, "skipped": "daily_limit", "reconciled": reconciled}

        try:
            approve_lead(connection, lead_id, auto=True)
            outcome = place(connection, lead_id)
        except LeadClaimLost:
            continue
        except Exception as error:
            row = connection.execute("SELECT status FROM leads WHERE id = ?", (lead_id,)).fetchone()
            if row and row[0] == "SUBMITTED":
                # The API may have succeeded just before a local reporting failure.
                sent += 1
                if notify:
                    notify(bid_success_text(connection, lead_id, auto=True))
                continue

            reason = str(error) if isinstance(error, (FreelancerError, ValueError)) else "bid gagal dikirim; periksa koneksi dan log"
            connection.execute(
                "UPDATE leads SET status = CASE WHEN status = 'APPROVED' THEN 'INTERESTED' ELSE status END, "
                "bid_auto = 0, bid_error = ? WHERE id = ? AND status <> 'SUBMITTED'",
                (reason[:500], lead_id),
            )
            connection.commit()
            if notify:
                notify(bid_failure_text(connection, lead_id, reason))
            failures += 1
            if any(marker in reason.lower() for marker in FATAL):
                set_setting(connection, "auto_bid_enabled", "0")
                if notify:
                    notify("⏸️ Auto-bid dimatikan karena masalah akun/token Freelancer. Perbaiki akses, lalu aktifkan kembali di Pengaturan Freelance.")
                return {"sent": sent, "skipped": "account_error", "reconciled": reconciled}
            if failures >= MAX_FAILURES_PER_PASS:
                break
            continue

        if outcome == "already":
            # The account already bid manually; record the platform state without counting it as auto.
            connection.execute("UPDATE leads SET bid_auto = 0 WHERE id = ?", (lead_id,))
            connection.commit()
            already_sent += 1
        else:
            sent += 1
        if notify:
            notify(bid_success_text(connection, lead_id, auto=(outcome != "already")))

    return {"sent": sent, "already_submitted": already_sent, "reconciled": reconciled}
