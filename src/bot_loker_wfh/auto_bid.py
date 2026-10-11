"""Hands-off freelance bidding: Cora's drafts that pass the guard rails are sent through the Freelancer API.

Everything is bounded by settings the owner controls (all stored in Supabase `app_settings`):
  auto_bid_enabled        "1" turns it on (default off)
  auto_bid_max_per_day    bids sent in any rolling 24 hours
  auto_bid_min_score      minimum relevance score of the project
  auto_bid_max_competitors  skip projects that already have more bids than this
  auto_bid_max_age_hours  only fresh projects (an early bid wins)
Only Freelancer.com (official API) is automatic. The first refusal from the platform stops the
run, and a refused project is never retried by itself; a token/quota problem switches auto-bid off
and tells the owner.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .database import Connection
from .form_agent.bid_terms import parse_budget
from .freelancer_api import FreelancerError
from .lead_desk import WHEN, approve_lead
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
    """One pass: send what the guard rails allow. Returns a summary for the log."""
    if reconcile is not None:
        try:
            reconcile(connection)  # settle claims left over by a crash before anything new goes out
        except Exception:
            pass
    summary: dict[str, Any] = {"sent": 0, "skipped": "off"}
    cfg = config(connection)
    if not cfg["enabled"] or place is None:
        return summary
    room = cfg["per_day"] - sent_last_24h(connection)
    if room <= 0:
        return {"sent": 0, "skipped": "daily_cap"}
    summary["skipped"] = None
    failures = 0
    for lead_id, title in candidates(connection, cfg, room + MAX_FAILURES_PER_PASS):
        if summary["sent"] + summary.get("already", 0) >= room:
            break
        try:
            approve_lead(connection, lead_id)  # validates and marks APPROVED
            outcome = place(connection, lead_id)  # official API; marks SUBMITTED
        except Exception as error:
            reason = str(error) if isinstance(error, (FreelancerError, ValueError)) else "gagal mengirim"
            connection.execute(
                "UPDATE leads SET status = 'INTERESTED', bid_error = ? WHERE id = ? AND status <> 'SUBMITTED'",
                (reason[:300], lead_id),
            )
            connection.commit()
            summary["error"] = reason
            fatal = any(word in reason.lower() for word in FATAL)
            if fatal:
                set_setting(connection, "auto_bid_enabled", "0")
            if notify:
                tail = "Auto-bid dimatikan; periksa lalu aktifkan lagi." if fatal else "Proyek ini dilewati; auto-bid tetap jalan."
                notify(f"⚠️ Auto-bid gagal untuk \"{title}\": {reason}\n{tail}")
            if fatal:
                break
            failures += 1
            if failures >= MAX_FAILURES_PER_PASS:
                break  # never hammer the platform
            continue
        if outcome == "already":  # the account already had a bid: record it, count it as nothing we sent
            summary["already"] = summary.get("already", 0) + 1
            if notify:
                notify(f"ℹ️ \"{title}\" sudah ada bid kamu sebelumnya; dicatat sebagai terkirim.")
            continue
        connection.execute("UPDATE leads SET bid_auto = 1 WHERE id = ?", (lead_id,))
        connection.commit()
        summary["sent"] += 1
        if notify:
            notify(f"🤖 Bid otomatis terkirim: \"{title}\"")
    return summary
