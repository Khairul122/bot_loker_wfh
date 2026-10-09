"""Serve the 3D office view with live counts from the local database."""

from __future__ import annotations

import json
import sqlite3
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .github_portfolio import load_portfolio, sync_portfolio
from .office_work import open_db
from .settings_store import DEFAULTS, get_setting, set_setting
from .status_transitions import InvalidTransitionError

OFFICE_DIR = Path(__file__).with_name("office")
HUNT_RESULT_LIMIT = 5


def _grouped(connection: sqlite3.Connection, sql: str) -> dict:
    try:
        rows = connection.execute(sql).fetchall()
    except sqlite3.OperationalError:
        return {}
    out: dict = {}
    for *keys, count in rows:
        node = out
        for key in keys[:-1]:
            node = node.setdefault(key, {})
        node[keys[-1]] = count
    return out


def collect_stats(connection: sqlite3.Connection) -> dict:
    """Aggregate counts only; never titles, descriptions, CVs or cover letters."""
    return {
        "jobs": _grouped(connection, "SELECT source, status, COUNT(*) FROM jobs GROUP BY 1, 2"),
        "applications": _grouped(connection, "SELECT status, COUNT(*) FROM applications GROUP BY 1"),
        "leads": _grouped(connection, "SELECT source, status, COUNT(*) FROM leads GROUP BY 1, 2"),
        "llm": _grouped(connection, "SELECT status, COUNT(*) FROM llm_calls GROUP BY 1"),
        "forms": _grouped(connection, "SELECT status, COUNT(*) FROM form_sessions GROUP BY 1"),
        "history": connection.execute(
            "SELECT COUNT(*) FROM application_status_history"
        ).fetchone()[0],
        "settings": _settings_payload(connection),
    }


def _settings_payload(connection: sqlite3.Connection) -> dict:
    """Current runtime-tunable settings (interval in hours, min bound for the UI)."""
    return {
        key: {"value": get_setting(connection, key), "min": lower}
        for key, (_, lower) in DEFAULTS.items()
    }


def hunt_leads(connection: sqlite3.Connection, lead_service, source: str) -> dict:
    """Run one real fetch of a freelance source and return its newest leads.

    Only public project data (title, budget, link) is returned, never CV content.
    """
    inserted = lead_service.collect().get(source, 0)
    rows = connection.execute(
        "SELECT title, budget, url, kind FROM leads WHERE source = ? "
        "ORDER BY fetched_at DESC, score DESC LIMIT ?",
        (source, HUNT_RESULT_LIMIT),
    ).fetchall()
    return {
        "inserted": inserted,
        "matched": inserted,
        "top": [
            {"title": title, "sub": budget or "", "url": url, "kind": kind}
            for title, budget, url, kind in rows
        ],
    }


def hunt_jobs(connection: sqlite3.Connection, source: str, fetcher, pipeline) -> dict:
    """Fetch one job source for real, score new jobs, return its newest candidates."""
    inserted = fetcher.fetch_and_store()
    matched = pipeline.process_discovered()["candidate"]
    rows = connection.execute(
        "SELECT title, company, location, apply_url FROM jobs "
        "WHERE source = ? AND status = 'CANDIDATE' "
        "ORDER BY fetched_at DESC, relevance_score DESC LIMIT ?",
        (source, HUNT_RESULT_LIMIT),
    ).fetchall()
    return {
        "inserted": inserted,
        "matched": matched,
        "top": [
            {"title": title, "sub": " · ".join(filter(None, (company, location))), "url": url, "kind": "job"}
            for title, company, location, url in rows
        ],
    }


RESULT_LIMIT = 25

# One query per kind of work; every row is (title, sub, url, tag, score, when, detail).
_RESULT_QUERIES = {
    "jobs": (
        "SELECT title, company || COALESCE(' · ' || location, ''), apply_url, status, relevance_score, "
        "fetched_at, filtered_reason FROM jobs WHERE source = ? ORDER BY fetched_at DESC LIMIT ?"
    ),
    "screened": (
        "SELECT title, company || ' · ' || source, apply_url, status, relevance_score, fetched_at, "
        "filtered_reason FROM jobs WHERE status != 'DISCOVERED' "
        "ORDER BY (status = 'CANDIDATE') DESC, fetched_at DESC LIMIT ?"
    ),
    "drafts": (
        "SELECT j.title, j.company, j.apply_url, a.status, j.relevance_score, a.created_at, a.cover_letter "
        "FROM applications a JOIN jobs j ON j.id = a.job_id ORDER BY a.created_at DESC LIMIT ?"
    ),
    "applied": (
        "SELECT j.title, j.company, j.apply_url, a.status, j.relevance_score, "
        "COALESCE(a.submitted_at, a.created_at), a.method FROM applications a JOIN jobs j ON j.id = a.job_id "
        "WHERE a.status NOT IN ('DRAFT_READY', 'PENDING_APPROVAL', 'REJECTED_BY_USER') "
        "ORDER BY COALESCE(a.submitted_at, a.created_at) DESC LIMIT ?"
    ),
    "tracking": (
        "SELECT j.title, j.company, j.apply_url, h.to_status, NULL, h.changed_at, h.from_status "
        "FROM application_status_history h JOIN applications a ON a.id = h.application_id "
        "JOIN jobs j ON j.id = a.job_id ORDER BY h.changed_at DESC LIMIT ?"
    ),
    "leads": (
        "SELECT title, COALESCE(budget, '') || ' · ' || source, url, status, score, fetched_at, kind "
        "FROM leads WHERE source = ? ORDER BY fetched_at DESC LIMIT ?"
    ),
}


def employee_results(connection: sqlite3.Connection, view: str, source: str | None = None) -> list[dict]:
    """Recent output of one kind of work, for the owner to review (never CV content)."""
    sql = _RESULT_QUERIES.get(view)
    if sql is None:
        return []
    params = (source, RESULT_LIMIT) if view in ("jobs", "leads") else (RESULT_LIMIT,)
    keys = ("title", "sub", "url", "tag", "score", "when", "detail")
    return [dict(zip(keys, row)) for row in connection.execute(sql, params).fetchall()]


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, work, **kwargs):
        self.work = work
        super().__init__(*args, directory=str(OFFICE_DIR), **kwargs)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _connect(self):
        return open_db(self.work.database_path)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/stats.json":
            with self._connect() as connection:
                return self._json(200, {**collect_stats(connection), "work": self.work.status()})
        if path == "/results.json":
            query = parse_qs(urlsplit(self.path).query)
            view, source = query.get("view", [""])[0], query.get("source", [None])[0]
            with self._connect() as connection:
                return self._json(200, {"items": employee_results(connection, view, source)})
        if path == "/github.json":
            data = load_portfolio()
            return self._json(200, {"username": data.get("username"), "synced_at": data.get("synced_at"),
                                    "repos": len(data.get("repos", []))})
        if path == "/leads.json":
            source = parse_qs(urlsplit(self.path).query).get("source", [None])[0]
            with self._connect() as connection:
                return self._json(200, self.work.leads(connection, source))
        if path == "/inbox.json":
            with self._connect() as connection:
                return self._json(200, self.work.inbox(connection))
        if path == "/settings.json":
            with self._connect() as connection:
                return self._json(200, _settings_payload(connection))
        return super().do_GET()

    def do_POST(self):
        # Other sites open in the browser must not trigger actions on the owner's machine.
        origin = self.headers.get("Origin")
        if origin and origin.split("://", 1)[-1] != self.headers.get("Host"):
            return self._json(403, {"error": "forbidden"})
        parts = self.path.strip("/").split("/")
        if parts == ["github", "sync"]:
            length = int(self.headers.get("Content-Length") or 0)
            username = str(json.loads(self.rfile.read(length) or b"{}").get("username") or "").strip()
            try:
                data = sync_portfolio(username)
            except ValueError:
                return self._json(400, {"error": "invalid_username"})
            except OSError:
                return self._json(502, {"error": "github_unreachable"})
            return self._json(200, {"username": username, "synced_at": data["synced_at"], "repos": len(data["repos"])})
        if parts == ["auto"]:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            self.work.set_auto(bool(body.get("on")))
            return self._json(200, self.work.status())
        if parts == ["settings"]:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            key = str(body.get("key") or "")
            if key not in DEFAULTS:
                return self._json(400, {"error": "unknown_setting"})
            try:
                with self._connect() as connection:
                    set_setting(connection, key, str(body.get("value")))
                    return self._json(200, _settings_payload(connection))
            except ValueError:
                return self._json(400, {"error": "value_out_of_range"})
        if len(parts) == 3 and parts[0] == "leads":
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            try:
                with self._connect() as connection:
                    return self._json(200, self.work.lead_action(connection, parts[1], parts[2], body))
            except (KeyError, ValueError):
                return self._json(404, {"error": "not_found"})
        if len(parts) == 3 and parts[0] == "inbox":
            try:
                with self._connect() as connection:
                    return self._json(200, self.work.decide(connection, parts[1], parts[2]))
            except InvalidTransitionError:
                return self._json(409, {"error": "stale"})
        if len(parts) == 2 and parts[0] == "hunt" and parts[1] in self.work.hunters:
            job = self.work.hunters[parts[1]]
        elif parts == ["inbox", "draft"]:
            job = lambda connection: {"drafted": self.work.draft_next(connection)}  # noqa: E731
        else:
            return self._json(404, {"error": "not_found"})
        if not self.work.lock.acquire(blocking=False):
            return self._json(409, {"error": "busy"})
        try:
            with self._connect() as connection:
                self._json(200, job(connection))
        except Exception as error:  # surfaced to the page as a sad employee, not a stack trace
            self._json(502, {"error": type(error).__name__})
        finally:
            self.work.lock.release()

    def log_message(self, *args):
        pass


def serve(work, port: int = 8765) -> None:
    # Bound to localhost only: the page shows a personal bot's pipeline and cover letters.
    server = ThreadingHTTPServer(("127.0.0.1", port), partial(_Handler, work=work))
    print(f"kantor 3D siap di http://127.0.0.1:{port}  (Ctrl+C untuk berhenti)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
