"""Freelance project desk: list leads, draft and revise proposals, mark interest, approve bids.

Proposals and bid terms are drafts for the owner. A bid is only sent after the owner approves it
in the office web UI (`approve_lead`), and only on the hosts in SUBMIT_HOSTS.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse
from .database import Connection
from collections import Counter
from collections.abc import Callable

from .cv_profile import SafeCvProfile
from .form_agent.bid_terms import BidTerms, choose_bid_terms, parse_bid_terms
from .github_portfolio import relevant_repos

LEAD_LIST_LIMIT = 100
# Platforms where an approved bid may be typed in and submitted for the owner.
SUBMIT_HOSTS = ("freelancer.com", "projects.co.id")
MIN_PROPOSAL_CHARS = 100


class RevisionFailed(RuntimeError):
    """The model could not produce a revised draft; the old draft is kept."""
INDONESIAN_SOURCES = frozenset({"projects.co.id", "telegram"})
LEAD_STATUSES = frozenset({"NEW", "INTERESTED", "IGNORED"})
# Common Indonesian function words; English posts almost never contain them.
INDONESIAN_WORDS = frozenset(
    "yang dan untuk dengan dari ini itu ada saya kami kita bisa akan sudah butuh "
    "membuat pembuatan buat aplikasi tidak atau juga sebuah pada dalam mohon harga "
    "dibutuhkan mencari cari jasa sistem informasi website nya secara agar supaya".split()
)


def is_indonesian(text: str, source: str = "") -> bool:
    """Language of the post itself; the source only breaks ties for very short posts."""
    words = re.findall(r"[a-z]+", text.lower())
    hits = sum(word in INDONESIAN_WORDS for word in words)
    if len(words) < 8:
        return hits >= 2 or source in INDONESIAN_SOURCES
    return hits / len(words) >= 0.06  # ponytail: stopword ratio, swap for a real detector if it misfires


def portfolio_stack(portfolio: dict, limit: int = 6) -> str:
    """Main languages across the owner's public repos, e.g. "PHP (80 repos), Dart (30 repos)"."""
    counts = Counter(r.get("language") for r in portfolio.get("repos", []) if r.get("language"))
    return ", ".join(f"{lang} ({n} repos)" for lang, n in counts.most_common(limit))


# posted_at comes from many sources with different offsets; compare real instants, not strings
_POSTED = "COALESCE(posted_at, fetched_at)"
WHEN = rf"(CASE WHEN {_POSTED} ~ '^\d{{4}}-\d{{2}}-\d{{2}}T' THEN {_POSTED}::timestamptz ELSE fetched_at::timestamptz END)"
FRESH = f"{WHEN} >= now() - interval '3 days'"
# board filters: "new" and "old" split untouched projects at 3 days
LEAD_VIEWS = {
    "all": "status != 'IGNORED'",
    "new": f"status = 'NEW' AND {FRESH}",
    "old": f"status = 'NEW' AND NOT {FRESH}",
    "interested": "status = 'INTERESTED'",
    "approved": "status IN ('APPROVED', 'SUBMITTED')",
    "proposal": "COALESCE(proposal, '') != '' AND status != 'IGNORED'",
    "ignored": "status = 'IGNORED'",
}


def list_leads(connection: Connection, source: str | None = None, view: str = "all") -> list[dict]:
    sql = (
        "SELECT id, source, kind, title, description, budget, url, status, posted_at, "
        f"fetched_at, proposal, bid_terms FROM leads WHERE {LEAD_VIEWS.get(view, LEAD_VIEWS['all'])}"
    )
    params: tuple = ()
    if source:
        sql += " AND source = ?"
        params = (source,)
    sql += (
        f" ORDER BY (status = 'INTERESTED') DESC, {WHEN} DESC LIMIT ?"
    )
    keys = ("id", "source", "kind", "title", "description", "budget", "url", "status",
            "posted_at", "fetched_at", "proposal", "bid_terms")
    rows = connection.execute(sql, (*params, LEAD_LIST_LIMIT)).fetchall()
    items = [{**dict(zip(keys, row)), "description": (row[4] or "")[:600]} for row in rows]
    for item in items:
        item["bid_terms"] = _terms_json(item["bid_terms"])
    return items


def _terms_json(raw: str | None) -> dict | None:
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def lead_counts(connection: Connection, source: str | None = None) -> dict[str, int]:
    """How many projects each board filter would show (for the filter chips)."""
    where, params = (" AND source = ?", (source,)) if source else ("", ())
    return {
        view: connection.execute(f"SELECT COUNT(*) FROM leads WHERE ({cond}){where}", params).fetchone()[0]
        for view, cond in LEAD_VIEWS.items()
    }


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
    title: str, description: str, budget: str | None, profile: SafeCvProfile, repos: list[dict], *,
    indonesian: bool, stack: str = "",
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
        f"Candidate: {profile.to_summary()}\nGitHub stack: {stack or '-'}\n\n"
        f"Candidate GitHub repos:\n{proof}"
    )


def draft_proposal(
    connection: Connection,
    lead_id: str,
    profile: SafeCvProfile,
    llm: Callable[[str], str] | None = None,
    portfolio: dict | None = None,
    *,
    mark_interested: bool = True,
    note: str = "",
) -> str:
    """Write (or, with the owner's `note`, revise) the proposal and Cora's suggested bid terms."""
    row = connection.execute(
        "SELECT title, description, source, budget, proposal FROM leads WHERE id = ?", (lead_id,)
    ).fetchone()
    if row is None:
        raise KeyError(lead_id)
    title, description, source, budget, previous = row
    note = note.strip()[:500]
    indonesian = is_indonesian(f"{title} {description}", source)
    repos = relevant_repos(portfolio or {}, f"{title} {description}")
    text = ""
    if llm is not None:
        try:
            prompt = proposal_prompt(
                title, description, budget, profile, repos,
                indonesian=indonesian, stack=portfolio_stack(portfolio or {}),
            )
            if note and (previous or "").strip():
                prompt += (
                    f"\n\nPrevious draft:\n{previous.strip()}\n\nThe owner asks for this revision: {note}\n"
                    "Rewrite the draft applying the revision. Keep every rule above and invent no facts."
                )
            elif note:
                prompt += f"\n\nThe owner adds this instruction: {note}"
            text = str(llm(prompt) or "").strip()
        except Exception:  # the template is always a safe fallback
            text = ""
    if note and not text:
        raise RevisionFailed("model tidak menjawab; draf lama dipertahankan")
    text = text or template_proposal(title, description, profile, repos, indonesian=indonesian)
    save_proposal(connection, lead_id, text, mark_interested=mark_interested)
    terms = choose_bid_terms(llm, title=title, description=description, budget=budget or "", note=note)
    if terms is not None:
        save_bid_terms(connection, lead_id, terms)
    return text


def comment_prompt(title: str, description: str, repos: list[dict], *, indonesian: bool) -> str:
    language = "Bahasa Indonesia yang santai tapi sopan" if indonesian else "friendly, natural English"
    proof = repos[0]["url"] if repos else "-"
    return (
        f"Write a short public comment on a freelance project post in {language}, 40-70 words, plain text.\n"
        "Show you read the post: mention one concrete detail from it, ask ONE clarifying question "
        "that helps scope the work, and (only if it fits) mention this related repo of mine: "
        f"{proof}. No price, no contact details, no 'hire me' pressure, no invented facts.\n\n"
        f"Project: {title}\nDescription: {description[:1200]}"
    )


def template_comment(title: str, repos: list[dict], *, indonesian: bool) -> str:
    proof = repos[0]["url"] if repos else ""
    if indonesian:
        text = f'Halo, saya tertarik dengan proyek "{title}". Boleh tahu fitur mana yang paling prioritas dan targetnya kapan?'
        return text + (f" Contoh proyek serupa yang pernah saya buat: {proof}" if proof else "")
    text = f'Hi, "{title}" looks like a good fit for me. Which feature matters most, and what is your target date?'
    return text + (f" Here is similar work I built: {proof}" if proof else "")


def draft_comment(
    connection: Connection,
    lead_id: str,
    llm: Callable[[str], str] | None = None,
    portfolio: dict | None = None,
) -> str:
    """A short public comment/question for the project post; saved in leads.comment."""
    row = connection.execute("SELECT title, description, source FROM leads WHERE id = ?", (lead_id,)).fetchone()
    if row is None:
        raise KeyError(lead_id)
    title, description, source = row
    indonesian = is_indonesian(f"{title} {description}", source)
    repos = relevant_repos(portfolio or {}, f"{title} {description}", limit=1)
    text = ""
    if llm is not None:
        try:
            text = str(llm(comment_prompt(title, description, repos, indonesian=indonesian)) or "").strip()
        except Exception:
            text = ""
    text = text or template_comment(title, repos, indonesian=indonesian)
    connection.execute("UPDATE leads SET comment = ? WHERE id = ?", (text, lead_id))
    connection.commit()
    return text


def save_proposal(
    connection: Connection, lead_id: str, text: str, *, mark_interested: bool = True
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


def save_bid_terms(connection: Connection, lead_id: str, terms: BidTerms) -> None:
    payload = json.dumps(
        {"hourly_rate": terms.hourly_rate, "weekly_limit": terms.weekly_limit,
         "duration_days": terms.duration_days, "milestones": terms.milestones}
    )
    connection.execute("UPDATE leads SET bid_terms = ? WHERE id = ?", (payload, lead_id))
    connection.commit()


def get_bid_terms(connection: Connection, lead_id: str) -> BidTerms | None:
    row = connection.execute("SELECT bid_terms FROM leads WHERE id = ?", (lead_id,)).fetchone()
    if not row or not row[0]:
        return None
    try:
        return parse_bid_terms(row[0])
    except ValueError:
        return None


def submit_allowed(url: str) -> bool:
    """Only https pages on the platforms the owner trusts for automatic bid submission."""
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(host == h or host.endswith("." + h) for h in SUBMIT_HOSTS)


def approve_lead(connection: Connection, lead_id: str) -> dict:
    """The owner approved the proposal and bid terms: mark the lead APPROVED for the form filler."""
    row = connection.execute("SELECT url, proposal, status FROM leads WHERE id = ?", (lead_id,)).fetchone()
    if row is None:
        raise KeyError(lead_id)
    url, proposal, status = row
    if status in ("SUBMITTED", "APPROVED"):
        raise ValueError("bid ini sudah disetujui/terkirim")
    if status == "IGNORED":
        raise ValueError("proyek ini diabaikan; kembalikan ke Baru dulu")
    if len((proposal or "").strip()) < MIN_PROPOSAL_CHARS:
        raise ValueError("proposal minimal 100 karakter sebelum dikirim")
    if not submit_allowed(url):
        raise ValueError("pengiriman otomatis hanya untuk Freelancer.com dan Projects.co.id; kirim manual")
    connection.execute("UPDATE leads SET status = 'APPROVED' WHERE id = ?", (lead_id,))
    connection.commit()
    return {"url": url}


def undrafted_leads(connection: Connection, limit: int) -> list[str]:
    """Best-scored new projects that have no proposal yet."""
    return [
        row[0]
        for row in connection.execute(
            "SELECT id FROM leads WHERE status = 'NEW' AND COALESCE(proposal, '') = '' "
            "ORDER BY score DESC, fetched_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    ]


def set_lead_status(connection: Connection, lead_id: str, status: str) -> None:
    if status not in LEAD_STATUSES:
        raise ValueError("unsupported lead status")
    updated = connection.execute("UPDATE leads SET status = ? WHERE id = ?", (status, lead_id)).rowcount
    connection.commit()
    if updated != 1:
        raise KeyError(lead_id)
