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
from urllib.request import Request, urlopen

from .database import Connection
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


def place_freelancer_bid(connection: Connection, lead_id: str, *, token: str, opener: Callable[..., Any] = urlopen) -> None:
    """Send the approved bid and mark the lead SUBMITTED. Raises FreelancerError with a clear reason."""
    row = connection.execute(
        "SELECT source, external_id, proposal, status FROM leads WHERE id = ?", (lead_id,)
    ).fetchone()
    if row is None:
        raise KeyError(lead_id)
    source, external_id, proposal, status = row
    if source != "freelancer" or not str(external_id).isdigit():
        raise FreelancerError("Proyek ini bukan proyek Freelancer.com")
    if status == "SUBMITTED":
        raise FreelancerError("Bid ini sudah terkirim")
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
    _call("POST", "/projects/0.1/bids/", token, {
        "project_id": int(external_id),
        "bidder_id": bidder_id(token, opener=opener),
        "amount": amount,
        "period": period,
        "milestone_percentage": 100,
        "description": proposal.strip(),
    }, opener=opener)
    connection.execute("UPDATE leads SET status = 'SUBMITTED' WHERE id = ?", (lead_id,))
    connection.commit()
