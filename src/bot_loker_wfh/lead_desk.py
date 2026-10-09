"""Freelance project desk: list leads, draft proposals, mark interest.

Proposals are drafts for the owner. Nothing here places a bid; the browser form
filler stops before the submit button and the owner sends the bid themselves.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from .cv_profile import SafeCvProfile
LEAD_LIST_LIMIT = 40
INDONESIAN_SOURCES = frozenset({"projects.co.id", "telegram"})
LEAD_STATUSES = frozenset({"NEW", "INTERESTED", "IGNORED"})


def list_leads(connection: sqlite3.Connection, source: str | None = None) -> list[dict]:
    sql = (
        "SELECT id, source, kind, title, description, budget, url, status, posted_at, "
        "fetched_at, proposal FROM leads WHERE status != 'IGNORED'"
    )
    params: tuple = ()
    if source:
        sql += " AND source = ?"
        params = (source,)
    sql += " ORDER BY (status = 'INTERESTED') DESC, COALESCE(posted_at, fetched_at) DESC LIMIT ?"
    keys = ("id", "source", "kind", "title", "description", "budget", "url", "status",
            "posted_at", "fetched_at", "proposal")
    rows = connection.execute(sql, (*params, LEAD_LIST_LIMIT)).fetchall()
    return [{**dict(zip(keys, row)), "description": (row[4] or "")[:600]} for row in rows]


def template_proposal(title: str, profile: SafeCvProfile, *, indonesian: bool) -> str:
    skills = ", ".join(profile.skills[:6]) or "web & mobile development"
    if indonesian:
        return (
            f"Halo, saya tertarik mengerjakan proyek \"{title}\".\n\n"
            f"Saya terbiasa bekerja dengan {skills}, jadi kebutuhan proyek ini sesuai dengan "
            "pengalaman saya. Saya akan mulai dengan memastikan detail kebutuhan, lalu "
            "mengirim progres secara berkala sampai selesai.\n\n"
            "Boleh saya tahu target waktu dan apakah sudah ada desain atau dokumen kebutuhan?\n\n"
            "Terima kasih."
        )
    return (
        f"Hi, I'd like to help with \"{title}\".\n\n"
        f"I work daily with {skills}, which fits what this project needs. I'll start by "
        "confirming the requirements, then share progress regularly until delivery.\n\n"
        "Could you share your timeline and whether designs or specs already exist?\n\n"
        "Thanks!"
    )


def proposal_prompt(title: str, description: str, budget: str | None, profile: SafeCvProfile, *, indonesian: bool) -> str:
    language = "Bahasa Indonesia yang sopan" if indonesian else "clear, friendly English"
    return (
        f"Write a freelance bid proposal in {language}, 120-180 words, plain text, no markdown.\n"
        "Use ONLY the candidate facts below; never invent clients, numbers or years.\n"
        "Open with the client's need, show 2-3 relevant skills, give a short approach, "
        "and end with one clarifying question.\n\n"
        f"Project: {title}\nBudget: {budget or '-'}\nDescription: {description[:1500]}\n\n"
        f"Candidate: {profile.to_summary()}"
    )


def draft_proposal(
    connection: sqlite3.Connection,
    lead_id: str,
    profile: SafeCvProfile,
    llm: Callable[[str], str] | None = None,
) -> str:
    row = connection.execute(
        "SELECT title, description, source, budget FROM leads WHERE id = ?", (lead_id,)
    ).fetchone()
    if row is None:
        raise KeyError(lead_id)
    title, description, source, budget = row
    indonesian = source in INDONESIAN_SOURCES
    text = ""
    if llm is not None:
        try:
            text = str(llm(proposal_prompt(title, description, budget, profile, indonesian=indonesian)) or "").strip()
        except Exception:  # the template is always a safe fallback
            text = ""
    text = text or template_proposal(title, profile, indonesian=indonesian)
    save_proposal(connection, lead_id, text)
    return text


def save_proposal(connection: sqlite3.Connection, lead_id: str, text: str) -> None:
    # writing a proposal means the owner is interested in the project
    updated = connection.execute(
        "UPDATE leads SET proposal = ?, status = CASE WHEN status = 'NEW' THEN 'INTERESTED' ELSE status END "
        "WHERE id = ?",
        (text.strip(), lead_id),
    ).rowcount
    connection.commit()
    if updated != 1:
        raise KeyError(lead_id)


def set_lead_status(connection: sqlite3.Connection, lead_id: str, status: str) -> None:
    if status not in LEAD_STATUSES:
        raise ValueError("unsupported lead status")
    updated = connection.execute("UPDATE leads SET status = ? WHERE id = ?", (status, lead_id)).rowcount
    connection.commit()
    if updated != 1:
        raise KeyError(lead_id)
