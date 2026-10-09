"""The owner's office: real performance reports, standing instructions and Q&A.

Every number in a report is counted from the bot's own tables over a time window.
Instructions are plain owner text that changes real work: Cora's prompts, the
order Sari drafts candidates in, and which hunt results a scout lists first.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from collections.abc import Callable
from datetime import datetime

DAILY_HOUR = 8  # local time; the morning report round starts after this
INSTRUCTION_LIMIT = 500
NOTE_LIMIT = 1000
QUESTION_LIMIT = 300

JOB_SCOUTS = {
    "reno": "remoteok", "rima": "remotive", "gery": "greenhouse",
    "leva": "lever", "kalia": "kalibrr", "dela": "dealls",
}
LEAD_SCOUTS = {"lido": "freelancer", "nara": "projects.co.id", "tama": "telegram"}
ROLES = {
    "tegar": "resepsionis Telegram yang mengantar notifikasi dan menjaga antrean persetujuan",
    "sari": "penilai skill yang memberi skor relevansi lowongan",
    "eli": "penjaga kelayakan yang menyaring lowongan tidak remote / tidak cocok",
    "cora": "penulis surat lamaran dan proposal freelance",
    "lulu": "asisten AI yang menjalankan panggilan model bahasa",
    "faris": "pengisi formulir lamaran di browser",
    "subi": "pengirim lamaran",
    "tara": "pemantau status lamaran",
    "ivan": "pelatih interview",
    **{e: f"pemburu lowongan di {s}" for e, s in JOB_SCOUTS.items()},
    **{e: f"pemburu proyek freelance di {s}" for e, s in LEAD_SCOUTS.items()},
}
EMPLOYEES = tuple(ROLES)
SOURCE_OWNER = {s: e for e, s in {**JOB_SCOUTS, **LEAD_SCOUTS}.items()}

_SINCE = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now', ?)"


def _n(connection: sqlite3.Connection, sql: str, *params) -> int:
    try:
        return connection.execute(sql, params).fetchone()[0] or 0
    except sqlite3.OperationalError:  # optional table missing in an old database
        return 0


def _cap(value: float) -> float:
    return max(0.0, min(1.0, value))


def measure(connection: sqlite3.Connection, employee: str, hours: int = 24) -> dict:
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


def _row(row) -> dict:
    keys = ("id", "employee", "kind", "hours", "score", "body", "rating", "note", "delivered_at", "created_at")
    item = dict(zip(keys, row))
    item.update(json.loads(item.pop("body")))
    return item


_COLUMNS = "id, employee, kind, hours, score, body, rating, note, delivered_at, created_at"


def create_report(connection: sqlite3.Connection, employee: str, *, hours: int = 24,
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


def get_report(connection: sqlite3.Connection, report_id: str) -> dict:
    row = connection.execute(f"SELECT {_COLUMNS} FROM office_reports WHERE id = ?", (report_id,)).fetchone()
    if row is None:
        raise KeyError(report_id)
    return _row(row)


def ensure_daily_reports(connection: sqlite3.Connection, now: datetime | None = None) -> list[dict]:
    """The morning round: one report per employee per local day, created once."""
    now = now or datetime.now()
    if now.hour < DAILY_HOUR:
        return []
    day = now.date().isoformat()
    done = {r[0] for r in connection.execute(
        "SELECT employee FROM office_reports WHERE kind = 'daily' AND day = ?", (day,))}
    return [create_report(connection, e, kind="daily", day=day) for e in EMPLOYEES if e not in done]


def list_reports(connection: sqlite3.Connection, employee: str | None = None, limit: int = 60) -> list[dict]:
    where, params = ("WHERE employee = ?", (employee,)) if employee else ("", ())
    rows = connection.execute(
        f"SELECT {_COLUMNS} FROM office_reports {where} ORDER BY created_at DESC LIMIT ?", (*params, limit)
    ).fetchall()
    return [_row(r) for r in rows]


def undelivered(connection: sqlite3.Connection) -> list[dict]:
    """Reports still to be walked to the owner's desk in 3D, oldest first."""
    rows = connection.execute(
        "SELECT id, employee, body FROM office_reports WHERE delivered_at IS NULL ORDER BY created_at LIMIT 40"
    ).fetchall()
    return [{"id": i, "employee": e, "lines": json.loads(b)["lines"]} for i, e, b in rows]


def tray_count(connection: sqlite3.Connection) -> int:
    """Delivered reports the owner has not rated yet: the paper stack on the desk."""
    return _n(connection, "SELECT COUNT(*) FROM office_reports WHERE delivered_at IS NOT NULL AND rating IS NULL "
                          "AND created_at >= strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-3 days')")


def mark_delivered(connection: sqlite3.Connection, report_id: str) -> None:
    get_report(connection, report_id)
    connection.execute(
        "UPDATE office_reports SET delivered_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') "
        "WHERE id = ? AND delivered_at IS NULL", (report_id,))
    connection.commit()


def review_report(connection: sqlite3.Connection, report_id: str, rating, note: str = "") -> dict:
    rating = int(rating)
    if not 1 <= rating <= 5:
        raise ValueError("rating must be 1..5")
    get_report(connection, report_id)
    connection.execute("UPDATE office_reports SET rating = ?, note = ? WHERE id = ?",
                       (rating, (note or "").strip()[:NOTE_LIMIT] or None, report_id))
    connection.commit()
    return get_report(connection, report_id)


def ratings(connection: sqlite3.Connection) -> dict:
    """Average owner rating over each employee's last 10 rated reports."""
    out = {}
    for employee in EMPLOYEES:
        rows = [r[0] for r in connection.execute(
            "SELECT rating FROM office_reports WHERE employee = ? AND rating IS NOT NULL "
            "ORDER BY created_at DESC LIMIT 10", (employee,))]
        if rows:
            out[employee] = {"avg": round(sum(rows) / len(rows), 2), "n": len(rows), "last": rows[0]}
    return out


# ---------------------------------------------------------------- instructions

def get_instruction(connection: sqlite3.Connection, employee: str) -> str:
    row = connection.execute("SELECT text FROM office_instructions WHERE employee = ?", (employee,)).fetchone()
    return row[0] if row else ""


def set_instruction(connection: sqlite3.Connection, employee: str, text: str) -> str:
    if employee not in ROLES:
        raise KeyError(employee)
    text = " ".join(str(text or "").split())[:INSTRUCTION_LIMIT]
    if text:
        connection.execute(
            "INSERT INTO office_instructions (employee, text) VALUES (?, ?) ON CONFLICT(employee) DO UPDATE "
            "SET text = excluded.text, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')", (employee, text))
    else:
        connection.execute("DELETE FROM office_instructions WHERE employee = ?", (employee,))
    connection.commit()
    return text


def instructions(connection: sqlite3.Connection) -> dict:
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


def instructed(llm: Callable[[str], str] | None, connection: sqlite3.Connection, employee: str):
    """Wrap an LLM so every prompt carries the owner's standing instruction for `employee`."""
    if llm is None:
        return None
    text = get_instruction(connection, employee)
    return _Instructed(llm, text) if text else llm


class _Instructed:
    def __init__(self, llm: Callable[[str], str], text: str) -> None:
        self.llm, self.text = llm, text

    def __call__(self, prompt: str) -> str:
        return self.llm(f"{prompt}\n\nOWNER INSTRUCTION (follow it unless it asks you to invent facts):\n{self.text}")

    @property
    def last_result(self):  # DraftService reads provider/model from here
        return getattr(self.llm, "last_result", None)


# ---------------------------------------------------------------- Q&A and digests

def ask(connection: sqlite3.Connection, llm: Callable[[str], str] | None, employee: str, question: str) -> dict:
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
         *day["lines"]])
    order = get_instruction(connection, employee)
    if llm is not None:
        prompt = (
            f"Kamu adalah karyawan virtual bernama {employee.title()}, {ROLES[employee]}, di bot pencari kerja milik owner.\n"
            "Jawab pertanyaan owner dalam Bahasa Indonesia santai, maksimal 3 kalimat. "
            "Gunakan HANYA fakta di bawah; jika tidak ada datanya, katakan terus terang.\n\n"
            f"FAKTA:\n{facts}\n"
            + (f"INSTRUKSI OWNER UNTUKMU: {order}\n" if order else "")
            + f"\nPERTANYAAN OWNER: {question}"
        )
        try:
            answer = str(llm(prompt) or "").strip()
            if answer:
                return {"answer": answer[:1200], "ai": True}
        except Exception:  # the plain facts are always a safe answer
            pass
    return {"answer": " ".join(day["lines"]) + " (AI belum aktif, ini data mentahnya.)", "ai": False}


def report_text(report: dict) -> str:
    metrics = " · ".join(f"{icon} {label}: {value}" for icon, label, value in report["metrics"])
    return f"📋 {report['employee'].title()} ({report['hours']} jam)\n{metrics}\n" + " ".join(report["lines"])


def digest_text(reports: list[dict], title: str = "Laporan kinerja tim") -> str:
    return f"🏢 {title}\n\n" + "\n\n".join(report_text(r) for r in reports)
