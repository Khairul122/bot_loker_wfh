"""Freelance project desk: list leads, draft proposals, mark interest.

Proposals are drafts for the owner. Nothing here places a bid; the browser form
filler stops before the submit button and the owner sends the bid themselves.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from .cv_profile import SafeCvProfile
from .github_portfolio import relevant_repos

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
    sql += (
        " ORDER BY (status = 'INTERESTED') DESC, (COALESCE(proposal, '') != '') DESC,"
        " COALESCE(posted_at, fetched_at) DESC LIMIT ?"
    )
    keys = ("id", "source", "kind", "title", "description", "budget", "url", "status",
            "posted_at", "fetched_at", "proposal")
    rows = connection.execute(sql, (*params, LEAD_LIST_LIMIT)).fetchall()
    return [{**dict(zip(keys, row)), "description": (row[4] or "")[:600]} for row in rows]


def _matched_skills(profile: SafeCvProfile, text: str, limit: int = 4) -> list[str]:
    lowered = text.lower()
    hits = [skill for skill in profile.skills if skill.lower() in lowered]
    return (hits + [s for s in profile.skills if s not in hits])[:limit]


def template_proposal(
    title: str, description: str, profile: SafeCvProfile, repos: list[dict], *, indonesian: bool
) -> str:
    """Offline fallback: hook, proof (real repos), plan, call to action."""
    skills = ", ".join(_matched_skills(profile, f"{title} {description}")) or "web & mobile development"
    proof = "\n".join(f"• {r['name']} ({r['language'] or 'code'}): {r['url']}" for r in repos)
    if indonesian:
        parts = [
            f'Halo! Saya sudah membaca kebutuhan "{title}" dan siap membantu sampai proyek ini benar-benar jalan.',
            f"Saya fokus di {skills}, dan pernah membangun proyek sejenis:\n{proof}" if proof
            else f"Saya fokus di {skills}, sesuai dengan kebutuhan proyek ini.",
            "Rencana kerja saya:\n"
            "1. Konfirmasi kebutuhan & prioritas fitur\n"
            "2. Kerjakan bertahap dengan progres yang bisa Anda cek langsung\n"
            "3. Uji, perbaiki masukan, lalu serah terima beserta dokumentasi",
            "Komunikasi cepat, kode rapi, dan revisi sampai sesuai. Saya bisa mulai hari ini.",
            "Boleh saya tahu target waktunya dan apakah sudah ada desain atau contoh yang Anda suka?",
        ]
    else:
        parts = [
            f'Hi! I\'ve read through "{title}" and I can take it from requirements to a working, tested delivery.',
            f"I specialise in {skills}, and I've built similar work you can check right now:\n{proof}" if proof
            else f"I specialise in {skills}, which is exactly what this project needs.",
            "How I'd approach it:\n"
            "1. Confirm scope and priorities with you\n"
            "2. Build in small milestones you can review\n"
            "3. Test, polish your feedback, and hand over with clear documentation",
            "Fast replies, clean maintainable code, and revisions until you're happy. I can start today.",
            "What's your target timeline, and do you already have designs or a reference you like?",
        ]
    return "\n\n".join(parts)


def proposal_prompt(
    title: str, description: str, budget: str | None, profile: SafeCvProfile, repos: list[dict], *, indonesian: bool
) -> str:
    language = "Bahasa Indonesia yang ramah dan profesional" if indonesian else "confident, friendly English"
    proof = "\n".join(
        f"- {r['name']} | {r['language'] or '-'} | {r['description'] or 'no description'} | {r['url']}"
        for r in repos
    ) or "- (none)"
    return (
        f"Write a winning freelance bid in {language}, 130-180 words, plain text (no markdown headings).\n"
        "Structure:\n"
        "1. Hook: one sentence that restates the client's goal and shows you understood it.\n"
        "2. Proof: name the 2-3 most relevant skills and cite the GitHub repos below as examples, "
        "with their full URL. Only cite repos that genuinely relate; skip them if none do.\n"
        "3. Plan: 3 short numbered steps or milestones.\n"
        "4. Value: communication, clean code, revisions; say you can start right away.\n"
        "5. Close with ONE specific question about the project.\n"
        "Rules: use ONLY the facts below. Never invent years of experience, client names, ratings, "
        "numbers or repos. No 'Dear Sir/Madam'. No price unless the budget is given.\n\n"
        f"Project: {title}\nBudget: {budget or '-'}\nDescription: {description[:1500]}\n\n"
        f"Candidate: {profile.to_summary()}\n\nCandidate GitHub repos:\n{proof}"
    )


def draft_proposal(
    connection: sqlite3.Connection,
    lead_id: str,
    profile: SafeCvProfile,
    llm: Callable[[str], str] | None = None,
    portfolio: dict | None = None,
    *,
    mark_interested: bool = True,
) -> str:
    row = connection.execute(
        "SELECT title, description, source, budget FROM leads WHERE id = ?", (lead_id,)
    ).fetchone()
    if row is None:
        raise KeyError(lead_id)
    title, description, source, budget = row
    indonesian = source in INDONESIAN_SOURCES
    repos = relevant_repos(portfolio or {}, f"{title} {description}")
    text = ""
    if llm is not None:
        try:
            prompt = proposal_prompt(title, description, budget, profile, repos, indonesian=indonesian)
            text = str(llm(prompt) or "").strip()
        except Exception:  # the template is always a safe fallback
            text = ""
    text = text or template_proposal(title, description, profile, repos, indonesian=indonesian)
    save_proposal(connection, lead_id, text, mark_interested=mark_interested)
    return text


def save_proposal(
    connection: sqlite3.Connection, lead_id: str, text: str, *, mark_interested: bool = True
) -> None:
    # the owner writing/asking for a proposal means interest; an automatic draft does not
    status_sql = "CASE WHEN status = 'NEW' THEN 'INTERESTED' ELSE status END" if mark_interested else "status"
    updated = connection.execute(
        f"UPDATE leads SET proposal = ?, status = {status_sql} WHERE id = ?",
        (text.strip(), lead_id),
    ).rowcount
    connection.commit()
    if updated != 1:
        raise KeyError(lead_id)


def undrafted_leads(connection: sqlite3.Connection, limit: int) -> list[str]:
    """Best-scored new projects that have no proposal yet."""
    return [
        row[0]
        for row in connection.execute(
            "SELECT id FROM leads WHERE status = 'NEW' AND COALESCE(proposal, '') = '' "
            "ORDER BY score DESC, fetched_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    ]


def set_lead_status(connection: sqlite3.Connection, lead_id: str, status: str) -> None:
    if status not in LEAD_STATUSES:
        raise ValueError("unsupported lead status")
    updated = connection.execute("UPDATE leads SET status = ? WHERE id = ?", (status, lead_id)).rowcount
    connection.commit()
    if updated != 1:
        raise KeyError(lead_id)
