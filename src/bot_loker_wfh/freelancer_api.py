"""Place an approved bid on Freelancer.com through its official API (no browser involved).

The token comes from FREELANCER_ACCESS_TOKEN in `.env`. Price, deadline and proposal are the
owner-approved values stored on the lead; the platform's own error text is passed on (it never
contains the token), so a rejected bid tells the owner exactly why.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .database import Connection
from .form_agent.bid_terms import parse_budget
from .lead_desk import get_bid_terms

API = "https://www.freelancer.com/api"
USER_AGENT = "bot-loker-wfh/0.1 (own account)"
_bidder_ids: dict[str, int] = {}


class FreelancerError(RuntimeError):
    """A bid problem the owner can read and act on."""


def _call(method: str, path: str, token: str, payload: dict | None = None, *, opener: Callable[..., Any] = urlopen) -> dict:
    request = Request(
        f"{API}{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        method=method,
        headers={"freelancer-oauth-v1": token, "Accept": "application/json",
                 "Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with opener(request, timeout=30) as response:
            return json.loads(response.read() or b"{}")
    except HTTPError as error:
        try:
            body = json.loads(error.read() or b"{}")
        except ValueError:
            body = {}
        if error.code in (401, 403) and not body.get("message"):
            raise FreelancerError("Token Freelancer ditolak atau kedaluwarsa; buat token baru dan perbarui FREELANCER_ACCESS_TOKEN") from None
        message = re.sub(r"\s+", " ", str(body.get("message") or f"HTTP {error.code}"))[:240]
        raise FreelancerError(f"Freelancer menolak bid: {message}") from None
    except (URLError, OSError, ValueError):
        raise FreelancerError("Freelancer tidak terjangkau; coba lagi sebentar lagi") from None


def bidder_id(token: str, *, opener: Callable[..., Any] = urlopen) -> int:
    if token not in _bidder_ids:
        result = _call("GET", "/users/0.1/self/", token, opener=opener).get("result") or {}
        if not result.get("id"):
            raise FreelancerError("Tidak bisa membaca akun Freelancer dari token ini")
        _bidder_ids[token] = int(result["id"])
    return _bidder_ids[token]


def has_bid(token: str, project_id: int, *, opener: Callable[..., Any] = urlopen) -> bool | None:
    """Does this account already have a bid on the project (made by the bot or by hand)? None = unknown."""
    try:
        query = urlencode([("projects[]", project_id), ("bidders[]", bidder_id(token, opener=opener))])
        result = _call("GET", f"/projects/0.1/bids/?{query}", token, opener=opener).get("result") or {}
    except FreelancerError:
        return None
    return bool(result.get("bids"))


def _mark_submitted(connection: Connection, lead_id: str) -> None:
    connection.execute(
        "UPDATE leads SET status = 'SUBMITTED', bid_error = NULL, bid_submitted_at = utc_now_iso() WHERE id = ?", (lead_id,)
    )
    connection.commit()


def place_freelancer_bid(connection: Connection, lead_id: str, *, token: str, opener: Callable[..., Any] = urlopen) -> str:
    """Send the approved bid and mark the lead SUBMITTED. Returns "sent", or "already" when the
    account already had a bid on the project. Raises FreelancerError with a clear reason."""
    row = connection.execute(
        "SELECT source, external_id, proposal, status, budget FROM leads WHERE id = ?", (lead_id,)
    ).fetchone()
    if row is None:
        raise KeyError(lead_id)
    source, external_id, proposal, status, budget_text = row
    if source != "freelancer" or not str(external_id).isdigit():
        raise FreelancerError("Proyek ini bukan proyek Freelancer.com")
    if status == "SUBMITTED":
        raise FreelancerError("Bid ini sudah terkirim")
    budget = parse_budget(budget_text)
    if budget is not None and budget.hourly:
        raise FreelancerError("Proyek per jam belum didukung pengiriman API; kirim manual lewat Buka proyek")
    terms = get_bid_terms(connection, lead_id)
    try:
        amount = float(terms.amount or terms.hourly_rate) if terms else 0.0
        period = int(float(terms.duration_days)) if terms else 0
    except ValueError:
        amount, period = 0.0, 0
    if amount <= 0 or period <= 0:
        raise FreelancerError("Isi harga dan tenggang waktu (hari) di Ajuan bid dulu")
    if len((proposal or "").strip()) < 100:
        raise FreelancerError("Proposal minimal 100 karakter")
    if budget is not None and budget.high is not None and not budget.low * 0.25 <= amount <= budget.high * 2:
        raise FreelancerError(f"Harga {amount:g} jauh di luar budget proyek ({budget.low:g}-{budget.high:g}); periksa angkanya")
    project_id = int(external_id)
    if has_bid(token, project_id, opener=opener):  # a bid made earlier, even by hand on the website
        _mark_submitted(connection, lead_id)
        return "already"
    payload = {
        "project_id": project_id,
        "bidder_id": bidder_id(token, opener=opener),
        "amount": amount,
        "period": period,
        "milestone_percentage": 100,
        "description": proposal.strip(),
    }
    try:
        _call("POST", "/projects/0.1/bids/", token, payload, opener=opener)
    except FreelancerError as error:
        # an answer lost on the way does not prove the bid failed: ask the platform before reporting a failure
        if "tidak terjangkau" in str(error) and has_bid(token, project_id, opener=opener):
            _mark_submitted(connection, lead_id)
            return "sent"
        raise
    _mark_submitted(connection, lead_id)
    return "sent"


STALE_CLAIM_MINUTES = 15


def reconcile_stuck(connection: Connection, token: str, *, opener: Callable[..., Any] = urlopen) -> int:
    """A claim that never finished (crash, power cut) is settled with the platform's own record."""
    rows = connection.execute(
        "SELECT id, external_id FROM leads WHERE source = 'freelancer' AND status = 'APPROVED' "
        "AND (bid_claimed_at IS NULL OR bid_claimed_at < utc_now_iso(?))", (f"-{STALE_CLAIM_MINUTES} minutes",),
    ).fetchall()
    fixed = 0
    for lead_id, external_id in rows:
        placed = has_bid(token, int(external_id), opener=opener) if str(external_id).isdigit() else False
        if placed is None:
            continue  # cannot tell right now; try again next pass
        if placed:
            _mark_submitted(connection, lead_id)
        else:
            connection.execute("UPDATE leads SET status = 'INTERESTED' WHERE id = ? AND status = 'APPROVED'", (lead_id,))
            connection.commit()
        fixed += 1
    # claims on other platforms (browser window) that nobody finished within an hour: open again, never guessed as sent
    fixed += connection.execute(
        "UPDATE leads SET status = 'INTERESTED' WHERE source <> 'freelancer' AND status = 'APPROVED' "
        "AND (bid_claimed_at IS NULL OR bid_claimed_at < utc_now_iso('-60 minutes'))"
    ).rowcount
    connection.commit()
    return fixed
