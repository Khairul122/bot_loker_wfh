"""The owner's office: real performance reports, standing instructions and Q&A.

Every number in a report is counted from the bot's own tables over a time window.
Instructions are plain owner text that changes real work: Cora's prompts, the
order Sari drafts candidates in, and which hunt results a scout lists first.
"""

from __future__ import annotations

import json
import re
from .database import Connection
from .company import (
    EMPLOYEES as EMPLOYEE_CATALOG,
    JOB_SCOUTS,
    LEAD_SCOUTS,
    ROLES as EMPLOYEE_ROLES,
    managed_division_for,
)
from .employee_memory import DRAFT_SOURCE, lessons_text, list_memories, remember
from .github_portfolio import MIN_MATCH, load_portfolio
import uuid
from collections.abc import Callable
from datetime import datetime

DAILY_HOUR = 8  # local time; the morning report round starts after this
INSTRUCTION_LIMIT = 500
NOTE_LIMIT = 1000
QUESTION_LIMIT = 300

ROLES = EMPLOYEE_ROLES
EMPLOYEES = tuple(ROLES)
SOURCE_OWNER = {s: e for e, s in {**JOB_SCOUTS, **LEAD_SCOUTS}.items()}

_SINCE = "utc_now_iso(?)"


def _n(connection: Connection, sql: str, *params) -> int:
    return connection.execute(sql, params).fetchone()[0] or 0


def _cap(value: float) -> float:
    return max(0.0, min(1.0, value))


def measure(connection: Connection, employee: str, hours: int = 24) -> dict:
    """What one employee really did in the last `hours`: metrics, lines, score 0..1."""
    w = f"-{int(hours)} hours"
    if employee in JOB_SCOUTS:
        src = JOB_SCOUTS[employee]
        found = _n(connection, f"SELECT COUNT(*) FROM jobs WHERE source = ? AND fetched_at >= {_SINCE}", src, w)
        match = _n(connection, f"SELECT COUNT(*) FROM jobs WHERE source = ? AND status = 'CANDIDATE' AND fetched_at >= {_SINCE}", src, w)
        return {
            "metrics": [["🔎", "Lowongan baru", found], ["✅", "Cocok", match]],
            "lines": [f"{found} lowongan baru dari {src}, {match} cocok untukmu." if found else f"Tidak ada lowongan baru dari {src}."],
            "score": 0.5 * _cap(found / 30) + 0.5 * _cap(match / 3),
        }
    if employee in LEAD_SCOUTS:
        src = LEAD_SCOUTS[employee]
        found = _n(connection, f"SELECT COUNT(*) FROM leads WHERE source = ? AND fetched_at >= {_SINCE}", src, w)
        liked = _n(connection, f"SELECT COUNT(*) FROM leads WHERE source = ? AND status = 'INTERESTED' AND fetched_at >= {_SINCE}", src, w)
        bids = _n(connection, f"SELECT COUNT(*) FROM leads WHERE source = ? AND proposal IS NOT NULL AND fetched_at >= {_SINCE}", src, w)
        return {
            "metrics": [["📌", "Proyek baru", found], ["💛", "Kamu minati", liked], ["✍️", "Ada draf bid", bids]],
            "lines": [f"{found} proyek baru dari {src}, {bids} sudah ada draf bid." if found else f"Tidak ada proyek baru dari {src}."],
            "score": 0.6 * _cap(found / 20) + 0.4 * _cap((liked + bids) / 3),
        }
    if employee == "sari":
        done = _n(connection, f"SELECT COUNT(*) FROM jobs WHERE status != 'DISCOVERED' AND fetched_at >= {_SINCE}", w)
        queue = _n(connection, "SELECT COUNT(*) FROM jobs WHERE status = 'DISCOVERED'")
        return {
            "metrics": [["🧮", "Dinilai", done], ["⏳", "Antrean", queue]],
            "lines": [f"{done} lowongan dinilai." + (f" Masih {queue} di antrean." if queue else " Antrean kosong.")],
            "score": 0.6 * _cap(done / 50) + (0.4 if not queue else 0.4 * _cap(done / (done + queue))),
        }
    if employee == "eli":
        ok = _n(connection, f"SELECT COUNT(*) FROM jobs WHERE status = 'CANDIDATE' AND fetched_at >= {_SINCE}", w)
        out = _n(connection, f"SELECT COUNT(*) FROM jobs WHERE status = 'FILTERED_OUT' AND fetched_at >= {_SINCE}", w)
        reasons = connection.execute(
            f"SELECT filtered_reason, COUNT(*) FROM jobs WHERE status = 'FILTERED_OUT' AND fetched_at >= {_SINCE} "
            "AND filtered_reason IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 3", (w,)
        ).fetchall()
        lines = [f"{ok} lolos, {out} saya saring."]
        if reasons:
            lines.append("Alasan terbanyak: " + ", ".join(f"{r} ({c})" for r, c in reasons) + ".")
        return {"metrics": [["✅", "Lolos", ok], ["🚫", "Disaring", out]], "lines": lines,
                "score": _cap((ok + out) / 40) * 0.6 + (0.4 if ok else 0)}
    if employee == "cora":
        drafts = _n(connection, f"SELECT COUNT(*) FROM applications WHERE created_at >= {_SINCE}", w)
        waiting = _n(connection, "SELECT COUNT(*) FROM jobs j LEFT JOIN applications a ON a.job_id = j.id "
                                 "WHERE j.status = 'CANDIDATE' AND a.id IS NULL")
        bids = _n(connection, f"SELECT COUNT(*) FROM leads WHERE proposal IS NOT NULL AND fetched_at >= {_SINCE}", w)
        return {
            "metrics": [["📝", "Surat lamaran", drafts], ["✍️", "Draf bid", bids], ["📥", "Belum ada surat", waiting]],
            "lines": [f"{drafts} surat lamaran dan {bids} draf bid selesai." + (f" {waiting} lowongan cocok masih menunggu surat." if waiting else "")],
            "score": 0.7 * _cap((drafts + bids) / 5) + (0.3 if not waiting else 0),
        }
    if employee == "bimo":
        bids = _n(connection, f"SELECT COUNT(*) FROM leads WHERE proposal IS NOT NULL AND fetched_at >= {_SINCE}", w)
        filled = _n(connection, f"SELECT COUNT(*) FROM leads WHERE status IN ('INTERESTED', 'SUBMITTED') AND proposal IS NOT NULL AND fetched_at >= {_SINCE}", w)
        return {
            "metrics": [["🤝", "Siap Ditawar", bids], ["🎯", "Diproses/Diajukan", filled]],
            "lines": [f"{filled} dari {bids} penawaran freelance siap diajukan." if bids else "Belum ada penawaran freelance yang diproses."],
            "score": 0.5 * _cap(bids / 3) + 0.5 * _cap(filled / max(bids, 1)),
        }
    if employee == "mira":
        return _freelance_division(connection, w, hours)
    if employee == "lulu":
        total = _n(connection, f"SELECT COUNT(*) FROM llm_calls WHERE created_at >= {_SINCE}", w)
        ok = _n(connection, f"SELECT COUNT(*) FROM llm_calls WHERE status = 'success' AND created_at >= {_SINCE}", w)
        ms = _n(connection, f"SELECT CAST(AVG(latency_ms) AS INTEGER) FROM llm_calls WHERE created_at >= {_SINCE}", w)
        return {
            "metrics": [["🤖", "Panggilan AI", total], ["✅", "Berhasil", ok], ["⏱️", "Rata-rata ms", ms]],
            "lines": [f"{ok} dari {total} panggilan AI berhasil." if total else "Tidak ada panggilan AI, surat memakai template."],
            "score": (0.3 + 0.7 * ok / total) if total else 0.2,
        }
    if employee == "faris":
        total = _n(connection, f"SELECT COUNT(*) FROM form_sessions WHERE started_at >= {_SINCE}", w)
        ok = _n(connection, f"SELECT COUNT(*) FROM form_sessions WHERE status = 'filled' AND started_at >= {_SINCE}", w)
        return {"metrics": [["🧾", "Formulir", total], ["✅", "Terisi", ok]],
                "lines": [f"{ok} dari {total} formulir terisi rapi." if total else "Tidak ada formulir yang perlu diisi."],
                "score": (0.3 + 0.7 * ok / total) if total else 0.3}
    if employee == "subi":
        sent = _n(connection, f"SELECT COUNT(*) FROM applications WHERE submitted_at >= {_SINCE}", w)
        failed = _n(connection, f"SELECT COUNT(*) FROM applications WHERE status = 'SUBMIT_FAILED' AND created_at >= {_SINCE}", w)
        return {"metrics": [["🚀", "Terkirim", sent], ["⚠️", "Gagal", failed]],
                "lines": [f"{sent} lamaran terkirim." + (f" {failed} gagal dikirim." if failed else "")],
                "score": _cap(sent / 3) * (0.5 if failed > sent else 1)}
    if employee == "tara":
        moves = _n(connection, f"SELECT COUNT(*) FROM application_status_history WHERE changed_at >= {_SINCE}", w)
        replies = _n(connection, "SELECT COUNT(*) FROM application_status_history WHERE to_status IN "
                                 f"('VIEWED', 'INTERVIEW', 'OFFER', 'REJECTED_BY_COMPANY') AND changed_at >= {_SINCE}", w)
        watching = _n(connection, "SELECT COUNT(*) FROM applications WHERE status IN ('SUBMITTED', 'VIEWED', 'INTERVIEW')")
        return {"metrics": [["🔁", "Perubahan status", moves], ["👀", "Respons perusahaan", replies], ["📬", "Dipantau", watching]],
                "lines": [f"{watching} lamaran saya pantau, {replies} respons baru."],
                "score": 0.4 * _cap(moves / 5) + 0.6 * _cap(replies / 2)}
    if employee == "ivan":
        interview = _n(connection, "SELECT COUNT(*) FROM applications WHERE status = 'INTERVIEW'")
        offer = _n(connection, "SELECT COUNT(*) FROM applications WHERE status = 'OFFER'")
        new = _n(connection, f"SELECT COUNT(*) FROM application_status_history WHERE to_status = 'INTERVIEW' AND changed_at >= {_SINCE}", w)
        return {"metrics": [["🎤", "Interview aktif", interview], ["🆕", "Undangan baru", new], ["🏆", "Offer", offer]],
                "lines": ["ADA OFFER! 🎉" if offer else f"{interview} interview perlu disiapkan." if interview else "Belum ada jadwal interview."],
                "score": _cap(0.2 + 0.3 * interview + 0.5 * offer)}
    if employee == "tegar":
        pending = _n(connection, "SELECT COUNT(*) FROM applications WHERE status = 'PENDING_APPROVAL'")
        decided = _n(connection, "SELECT COUNT(*) FROM application_status_history WHERE changed_by = 'user' "
                                 f"AND to_status IN ('APPROVED', 'REJECTED_BY_USER') AND changed_at >= {_SINCE}", w)
        return {"metrics": [["⏳", "Menunggu kamu", pending], ["🗳️", "Kamu putuskan", decided]],
                "lines": [f"{pending} lamaran menunggu persetujuanmu." if pending else "Tidak ada yang menunggu persetujuan."],
                "score": 0.5 + 0.5 * _cap(decided / 3) if not pending else 0.4 * _cap(decided / max(pending, 1))}
    raise KeyError(employee)


FREELANCE_TEAM = (("lido", "Lido"), ("nara", "Nara"), ("tama", "Tama"), ("bimo", "Bimo"))


def _ago(minutes: float) -> str:
    return f"{int(minutes)} mnt lalu" if minutes < 60 else f"{int(minutes // 60)} jam lalu" if minutes < 1440 else f"{int(minutes // 1440)} hari lalu"


def _freelance_division(connection: Connection, w: str, hours: int) -> dict:
    """The manager's report: the whole freelance division in one place, counted from the leads table."""
    from .auto_bid import config as auto_config, sent_last_24h

    found = _n(connection, f"SELECT COUNT(*) FROM leads WHERE fetched_at >= {_SINCE}", w)
    drafts = _n(connection, f"SELECT COUNT(*) FROM leads WHERE proposal IS NOT NULL AND fetched_at >= {_SINCE}", w)
    sent = _n(connection, f"SELECT COUNT(*) FROM leads WHERE bid_submitted_at >= {_SINCE}", w)
    auto = _n(connection, f"SELECT COUNT(*) FROM leads WHERE bid_auto = 1 AND bid_submitted_at >= {_SINCE}", w)
    refused = _n(connection, f"SELECT COUNT(*) FROM leads WHERE bid_error IS NOT NULL AND bid_claimed_at >= {_SINCE}", w)
    waiting = _n(connection, "SELECT COUNT(*) FROM leads WHERE proposal IS NOT NULL AND status IN ('NEW', 'INTERESTED') AND bid_error IS NULL")
    lines = [f"Divisi freelance {hours} jam terakhir: {found} proyek baru, {drafts} draf bid, {sent} bid terkirim ({auto} otomatis)."]
    scores = []
    for employee, name in FREELANCE_TEAM:
        part = measure(connection, employee, hours)
        scores.append(part["score"])
        lines.append(f"• {name}: " + (part["lines"][0] if part["lines"] else "-"))
    cfg = auto_config(connection)
    if cfg["enabled"]:
        lines.append(f"🤖 Auto-bid aktif: {sent_last_24h(connection)} dari {cfg['per_day']} jatah bid 24 jam terpakai.")
    else:
        lines.append(f"⏸️ Auto-bid mati: {waiting} draf menunggu persetujuanmu." if waiting else "⏸️ Auto-bid mati.")
    if refused:
        reasons = connection.execute(
            f"SELECT bid_error, COUNT(*) FROM leads WHERE bid_error IS NOT NULL AND bid_claimed_at >= {_SINCE} GROUP BY 1 ORDER BY 2 DESC LIMIT 2", (w,)
        ).fetchall()
        lines.append(f"⚠️ {refused} bid ditolak platform: " + "; ".join(f"{r[:90]} ({c}x)" for r, c in reasons))
    recent = connection.execute(
        "SELECT title, budget, bid_auto, bid_terms, EXTRACT(EPOCH FROM (now() - bid_submitted_at::timestamptz)) / 60 "
        "FROM leads WHERE bid_submitted_at IS NOT NULL ORDER BY bid_submitted_at DESC LIMIT 5"
    ).fetchall()
    for title, budget, is_auto, terms, minutes in recent:
        amount = ""
        try:
            amount = " · harga " + json.loads(terms)["amount"] if terms and json.loads(terms).get("amount") else ""
        except ValueError:
            pass
        lines.append(f"🚀 {title[:60]}{amount} · {_ago(minutes)}{' 🤖' if is_auto else ''}")
    team = sum(scores) / len(scores) if scores else 0.0
    quality = 1.0 if not refused else max(0.0, 1 - refused / max(sent + refused, 1))
    return {
        "metrics": [["📌", "Proyek baru", found], ["✍️", "Draf bid", drafts], ["🚀", "Bid terkirim", sent],
                    ["🤖", "Otomatis", auto], ["⚠️", "Ditolak", refused], ["⏳", "Menunggu", waiting]],
        "lines": lines,
        "score": 0.35 * _cap(sent / 3) + 0.25 * team + 0.2 * _cap(drafts / 5) + 0.2 * quality,
    }


def _row(row) -> dict:
    keys = ("id", "employee", "kind", "hours", "score", "body", "rating", "note", "delivered_at", "created_at")
    item = dict(zip(keys, row))
    item.update(json.loads(item.pop("body")))
    return item


_COLUMNS = "id, employee, kind, hours, score, body, rating, note, delivered_at, created_at"


def create_report(connection: Connection, employee: str, *, hours: int = 24,
                  kind: str = "manual", day: str | None = None) -> dict:
    data = measure(connection, employee, hours)
    report_id = str(uuid.uuid4())
    connection.execute(
        "INSERT INTO office_reports (id, employee, kind, day, hours, score, body) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (report_id, employee, kind, day, hours, round(data["score"], 3),
         json.dumps({"metrics": data["metrics"], "lines": data["lines"]}, ensure_ascii=False)),
    )
    connection.commit()
    return get_report(connection, report_id)


def get_report(connection: Connection, report_id: str) -> dict:
    row = connection.execute(f"SELECT {_COLUMNS} FROM office_reports WHERE id = ?", (report_id,)).fetchone()
    if row is None:
        raise KeyError(report_id)
    return _row(row)


def ensure_daily_reports(connection: Connection, now: datetime | None = None) -> list[dict]:
    """The morning round: one report per employee per local day, created once."""
    now = now or datetime.now()
    if now.hour < DAILY_HOUR:
        return []
    day = now.date().isoformat()
    done = {r[0] for r in connection.execute(
        "SELECT employee FROM office_reports WHERE kind = 'daily' AND day = ?", (day,))}
    return [create_report(connection, e, kind="daily", day=day) for e in EMPLOYEES if e not in done]


def list_reports(connection: Connection, employee: str | None = None, limit: int = 60) -> list[dict]:
    where, params = ("WHERE employee = ?", (employee,)) if employee else ("", ())
    rows = connection.execute(
        f"SELECT {_COLUMNS} FROM office_reports {where} ORDER BY created_at DESC LIMIT ?", (*params, limit)
    ).fetchall()
    return [_row(r) for r in rows]


def undelivered(connection: Connection) -> list[dict]:
    """Reports still to be walked to the owner's desk in 3D, oldest first."""
    rows = connection.execute(
        "SELECT id, employee, body FROM office_reports WHERE delivered_at IS NULL ORDER BY created_at LIMIT 40"
    ).fetchall()
    return [{"id": i, "employee": e, "lines": json.loads(b)["lines"]} for i, e, b in rows]


def tray_count(connection: Connection) -> int:
    """Delivered reports the owner has not rated yet: the paper stack on the desk."""
    return _n(connection, "SELECT COUNT(*) FROM office_reports WHERE delivered_at IS NOT NULL AND rating IS NULL "
                          "AND created_at >= utc_now_iso('-3 days')")


def mark_delivered(connection: Connection, report_id: str) -> None:
    get_report(connection, report_id)
    connection.execute(
        "UPDATE office_reports SET delivered_at = utc_now_iso() "
        "WHERE id = ? AND delivered_at IS NULL", (report_id,))
    connection.commit()


def review_report(connection: Connection, report_id: str, rating, note: str = "") -> dict:
    rating = int(rating)
    if not 1 <= rating <= 5:
        raise ValueError("rating must be 1..5")
    get_report(connection, report_id)
    connection.execute("UPDATE office_reports SET rating = ?, note = ? WHERE id = ?",
                       (rating, (note or "").strip()[:NOTE_LIMIT] or None, report_id))
    connection.commit()
    report = get_report(connection, report_id)
    _learn_from_review(connection, report)
    return report


def _learn_from_review(connection: Connection, report: dict) -> None:
    """The owner's grade becomes a lesson the employee carries into later prompts."""
    rating, note = report["rating"], report.get("note") or ""
    if rating <= 2:
        kind, importance = "correction", 0.9 if note else 0.7
        content = f"Laporan dinilai rendah ({rating}/5)." + (f" Catatan owner: {note}" if note else "")
    elif rating >= 4:
        kind, importance = "outcome", 0.8 if note else 0.6
        content = f"Laporan dinilai bagus ({rating}/5), pertahankan." + (f" Catatan owner: {note}" if note else "")
    else:
        kind, importance = "observation", 0.4
        content = f"Laporan dinilai cukup ({rating}/5)." + (f" Catatan owner: {note}" if note else "")
    remember(connection, report["employee"], content, kind=kind, source=f"report:{report['id']}",
             importance=importance, replace_source=True)


def ratings(connection: Connection) -> dict:
    """Average owner rating over each employee's last 10 rated reports."""
    out = {}
    for employee in EMPLOYEES:
        rows = [r[0] for r in connection.execute(
            "SELECT rating FROM office_reports WHERE employee = ? AND rating IS NOT NULL "
            "ORDER BY created_at DESC LIMIT 10", (employee,))]
        if rows:
            out[employee] = {"avg": round(sum(rows) / len(rows), 2), "n": len(rows), "last": rows[0]}
    return out


def profile(connection: Connection, employee: str) -> dict:
    """One employee's own page: today vs this week vs this month, score trend, owner feedback."""
    if employee not in ROLES:
        raise KeyError(employee)
    history = [
        {"score": score, "rating": rating, "at": at}
        for score, rating, at in reversed(connection.execute(
            "SELECT score, rating, created_at FROM office_reports WHERE employee = ? "
            "ORDER BY created_at DESC LIMIT 20", (employee,)).fetchall())
    ]
    notes = [
        {"rating": r, "note": n, "at": at} for r, n, at in connection.execute(
            "SELECT rating, note, created_at FROM office_reports WHERE employee = ? AND note IS NOT NULL "
            "ORDER BY created_at DESC LIMIT 5", (employee,)).fetchall()
    ]
    managed_division = managed_division_for(employee)
    team = None
    if managed_division:
        team = {
            "id": managed_division["id"],
            "name": managed_division["name"],
            "manager": employee,
            "team": [
                {
                    "employee": member["id"],
                    "name": member["name"],
                    "role": member["title"],
                    **measure(connection, member["id"], 24),
                }
                for member in EMPLOYEE_CATALOG
                if member["division"] == managed_division["id"]
            ],
        }
    return {
        "employee": employee,
        "role": ROLES[employee],
        "periods": {label: measure(connection, employee, hours) for label, hours in
                    (("24 jam", 24), ("7 hari", 24 * 7), ("30 hari", 24 * 30))},
        "history": history,
        "notes": notes,
        "rating": ratings(connection).get(employee),
        "instruction": get_instruction(connection, employee),
        "managed_division": team,
    }


# ---------------------------------------------------------------- instructions

def get_instruction(connection: Connection, employee: str) -> str:
    row = connection.execute("SELECT text FROM office_instructions WHERE employee = ?", (employee,)).fetchone()
    return row[0] if row else ""


def set_instruction(connection: Connection, employee: str, text: str) -> str:
    if employee not in ROLES:
        raise KeyError(employee)
    text = " ".join(str(text or "").split())[:INSTRUCTION_LIMIT]
    if text:
        connection.execute(
            "INSERT INTO office_instructions (employee, text) VALUES (?, ?) ON CONFLICT(employee) DO UPDATE "
            "SET text = excluded.text, updated_at = utc_now_iso()", (employee, text))
    else:
        connection.execute("DELETE FROM office_instructions WHERE employee = ?", (employee,))
    connection.commit()
    return text


def instructions(connection: Connection) -> dict:
    return dict(connection.execute("SELECT employee, text FROM office_instructions").fetchall())


def keywords(text: str) -> list[str]:
    """'fokus Python, Django; remote' -> ['python', 'django', 'remote'] (stop words are short)."""
    return [w for w in re.findall(r"[a-z0-9.+#-]+", (text or "").lower()) if len(w) >= 3 and w not in _STOP]


_STOP = {"yang", "dan", "untuk", "dengan", "fokus", "cari", "lowongan", "proyek", "the", "and", "only", "saja", "lebih"}


def keyword_hits(text: str, words: list[str]) -> int:
    low = (text or "").lower()
    return sum(1 for w in words if w in low)


def prioritize(items: list[dict], words: list[str]) -> list[dict]:
    """Stable: items matching more owner keywords first, original order otherwise."""
    if not words:
        return items
    return sorted(items, key=lambda i: -keyword_hits(f"{i.get('title', '')} {i.get('sub', '')}", words))


def instructed(llm: Callable[[str], str] | None, connection: Connection, employee: str):
    """Wrap an LLM so every prompt carries the owner's standing instruction for `employee`."""
    if llm is None:
        return None
    text, lessons = get_instruction(connection, employee), lessons_text(connection, employee)
    memory = "\n".join(part for part in (text, lessons) if part)
    task_llm = llm
    if hasattr(llm, "for_task"):
        task_llm = llm.for_task(
            "draft", persona=employee, memory_context=memory,
            session_key=f"loker:employee:{employee}"
        )
    elif hasattr(llm, "with_context"):
        task_llm = llm.with_context(
            persona=employee, memory_context=memory,
            session_key=f"loker:employee:{employee}"
        )
    return _Instructed(task_llm, text, lessons, connection, employee)


class _Instructed:
    def __init__(self, llm, text: str, lessons: str, connection, employee: str) -> None:
        self.llm, self.text, self.lessons = llm, text, lessons
        self.connection, self.employee = connection, employee

    def __call__(self, prompt: str) -> str:
        if self.text:
            prompt += f"\n\nOWNER INSTRUCTION (follow it unless it asks you to invent facts):\n{self.text}"
        if self.lessons:
            prompt += f"\n\nYOUR PAST LESSONS (from owner feedback; apply them, do not repeat past mistakes):\n{self.lessons}"
        return self.llm(prompt)

    def with_context(self, **context):
        employee = context.pop("persona", self.employee)
        text = get_instruction(self.connection, employee)
        lessons = lessons_text(self.connection, employee)
        runner = self.llm
        if hasattr(runner, "with_context"):
            values = {
                "persona": employee,
                "memory_context": "\n".join(part for part in (text, lessons) if part),
                "session_key": f"loker:employee:{employee}",
            }
            values.update(context)
            runner = runner.with_context(**values)
        return _Instructed(runner, text, lessons, self.connection, employee)

    @property
    def last_result(self):  # DraftService reads provider/model from here
        return getattr(self.llm, "last_result", None)


# ---------------------------------------------------------------- Q&A and digests

def github_facts(connection: Connection) -> list[str]:
    """What Cora knows about the owner's GitHub: sync state, the repo rule, and her recent repo choices."""
    portfolio = load_portfolio(connection)
    if not portfolio.get("repos"):
        return ["GitHub: belum ada data repo yang disinkronkan, jadi draf tidak mengutip repo."]
    lines = [
        f"GitHub: akun {portfolio.get('username') or '-'}, {len(portfolio['repos'])} repo publik, "
        f"terakhir disinkronkan {portfolio.get('synced_at') or '-'} (otomatis tiap 6 jam).",
        f"Aturan repo: draf hanya mengutip repo dengan skor kecocokan minimal {MIN_MATCH}% terhadap proyek klien "
        "(topik 70, kebaruan 10, bahasa 10, kelengkapan deskripsi 10; kata umum seperti web/backend/api tidak dihitung).",
    ]
    recent = list_memories(connection, "cora", limit=5, source_prefix=DRAFT_SOURCE)
    recent.sort(key=lambda m: m["created_at"], reverse=True)
    return lines + [f"Draf terbaru: {m['content']}" for m in recent]


def ask(connection: Connection, llm: Callable[[str], str] | None, employee: str, question: str) -> dict:
    """Answer the owner's question from this employee's real numbers; the LLM only phrases it."""
    if employee not in ROLES:
        raise KeyError(employee)
    question = " ".join(str(question or "").split())[:QUESTION_LIMIT]
    if not question:
        raise ValueError("empty question")
    day, week = measure(connection, employee, 24), measure(connection, employee, 24 * 7)
    facts = "\n".join(
        [f"24 jam: " + ", ".join(f"{label} {value}" for _, label, value in day["metrics"]),
         f"7 hari: " + ", ".join(f"{label} {value}" for _, label, value in week["metrics"]),
         *day["lines"],
         *(github_facts(connection) if employee == "cora" else [])])
    order = get_instruction(connection, employee)
    lessons = lessons_text(connection, employee)
    if llm is not None:
        prompt = (
            f"Kamu adalah karyawan virtual bernama {employee.title()}, {ROLES[employee]}, di bot pencari kerja milik owner.\n"
            "Jawab pertanyaan owner dalam Bahasa Indonesia santai, maksimal 3 kalimat. "
            "Gunakan HANYA fakta di bawah; jika tidak ada datanya, katakan terus terang.\n\n"
            f"FAKTA:\n{facts}\n"
            + (f"INSTRUKSI OWNER UNTUKMU: {order}\n" if order else "")
            + (f"PELAJARAN DARI FEEDBACK OWNER SEBELUMNYA:\n{lessons}\n" if lessons else "")
            + f"\nPERTANYAAN OWNER: {question}"
        )
        try:
            employee_llm = llm
            memory = "\n".join(part for part in (order, lessons) if part)
            if hasattr(llm, "with_context"):
                employee_llm = llm.with_context(
                    persona=employee,
                    memory_context=memory,
                    session_key=f"loker:employee:{employee}",
                    session_id=f"loker-owner-chat-{employee}",
                    system_prompt="Answer only from the supplied application facts; these override recalled conversation details.",
                )
            answer = str(employee_llm(prompt) or "").strip()
            if answer:
                return {"answer": answer[:1200], "ai": True}
        except Exception:  # the plain facts are always a safe answer
            pass
    plain = [*day["lines"], *(github_facts(connection) if employee == "cora" else [])]
    return {"answer": " ".join(plain) + " (AI belum aktif, ini data mentahnya.)", "ai": False}


INSTINCT_ZONES = ("pond", "roof", "cafe", "arena", "picnic", "sofa", "swing", "stay")


def instinct(connection: Connection, llm: Callable[[str], str] | None, employee: str, ctx: dict) -> dict | None:
    """One employee decides what to do in a work break, using their own lessons. None = no AI answer."""
    if employee not in ROLES or llm is None:
        return None
    clean = lambda v, n: " ".join(str(v or "").split())[:n]  # noqa: E731
    mates = ", ".join(clean(m, 30) for m in list(ctx.get("nearbyColleagues") or [])[:5]) or "tidak ada"
    recent = measure(connection, employee, 24)
    pipeline = "\n".join(
        ["Metrik pipeline 24 jam: " + ", ".join(f"{label} {value}" for _, label, value in recent["metrics"]),
         *recent["lines"]]
    )[:2500]
    prompt = (
        f"Kamu {employee.title()}, {ROLES[employee]}, karyawan virtual di kantor owner. Kamu sedang punya waktu luang.\n"
        f"Suasana hati: {clean(ctx.get('mood'), 20)}. Waktu: {clean(ctx.get('timeOfDay'), 10)}. "
        f"Posisi: {clean(ctx.get('currentZone'), 40)}. Rekan di dekatmu: {mates}.\n"
        f"Tinjau data pipeline aktual berikut dan suarakan satu saran atau alert yang didukung bukti; jangan mengubah data/status apa pun.\n{pipeline}\n"
        f"Pilih SATU tempat dari: {', '.join(INSTINCT_ZONES)} (stay = tetap bekerja di mejamu). "
        "Pertimbangkan pelajaran dan feedback owner: kalau laporanmu sering dinilai rendah, pilih stay untuk memperbaikinya.\n"
        'Balas HANYA JSON: {"zone": "<pilihan>", "thought": "<isi hati, maks 12 kata, Bahasa Indonesia santai>"}'
    )
    try:
        raw = str(instructed(llm, connection, employee)(prompt) or "")
        data = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except Exception:
        return None
    zone = data.get("zone") if isinstance(data, dict) else None
    if zone not in INSTINCT_ZONES:
        return None
    return {"zone": zone, "thought": clean(data.get("thought"), 120)}


def report_text(report: dict) -> str:
    metrics = " · ".join(f"{icon} {label}: {value}" for icon, label, value in report["metrics"])
    return f"📋 {report['employee'].title()} ({report['hours']} jam)\n{metrics}\n" + " ".join(report["lines"])


def digest_text(reports: list[dict], title: str = "Laporan kinerja tim") -> str:
    return f"🏢 {title}\n\n" + "\n\n".join(report_text(r) for r in reports)
