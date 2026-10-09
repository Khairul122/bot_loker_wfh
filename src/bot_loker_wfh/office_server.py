"""Serve the 3D office view with live counts from the local database."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

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
        "leads": _grouped(connection, "SELECT status, COUNT(*) FROM leads GROUP BY 1"),
        "llm": _grouped(connection, "SELECT status, COUNT(*) FROM llm_calls GROUP BY 1"),
        "forms": _grouped(connection, "SELECT status, COUNT(*) FROM form_sessions GROUP BY 1"),
        "history": connection.execute(
            "SELECT COUNT(*) FROM application_status_history"
        ).fetchone()[0],
    }


def hunt_freelancer(connection: sqlite3.Connection, lead_service) -> dict:
    """Run one real Freelancer.com fetch and return what is now newest for that source.

    Only public project data (title, budget, link) is returned, never CV content.
    """
    inserted = lead_service.collect().get("freelancer", 0)
    rows = connection.execute(
        "SELECT title, budget, url, kind FROM leads WHERE source = 'freelancer' "
        "ORDER BY fetched_at DESC, score DESC LIMIT ?",
        (HUNT_RESULT_LIMIT,),
    ).fetchall()
    return {
        "inserted": inserted,
        "top": [dict(zip(("title", "budget", "url", "kind"), row)) for row in rows],
    }


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, database_path: Path, make_lead_service, hunt_lock, **kwargs):
        self.database_path = database_path
        self.make_lead_service = make_lead_service
        self.hunt_lock = hunt_lock
        super().__init__(*args, directory=str(OFFICE_DIR), **kwargs)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] != "/stats.json":
            return super().do_GET()
        with sqlite3.connect(self.database_path) as connection:
            self._json(200, collect_stats(connection))

    def do_POST(self):
        if self.path != "/hunt/freelancer":
            return self._json(404, {"error": "not_found"})
        # Other sites open in the browser must not trigger fetches on the owner's machine.
        origin = self.headers.get("Origin")
        if origin and origin.split("://", 1)[-1] != self.headers.get("Host"):
            return self._json(403, {"error": "forbidden"})
        if not self.hunt_lock.acquire(blocking=False):
            return self._json(409, {"error": "busy"})
        try:
            with sqlite3.connect(self.database_path) as connection:
                self._json(200, hunt_freelancer(connection, self.make_lead_service(connection)))
        except Exception as error:  # surfaced to the page as a sad employee, not a stack trace
            self._json(502, {"error": type(error).__name__})
        finally:
            self.hunt_lock.release()

    def log_message(self, *args):
        pass


def serve(
    database_path: Path,
    make_lead_service: Callable[[sqlite3.Connection], object],
    port: int = 8765,
) -> None:
    # Bound to localhost only: the page exposes pipeline counts of a personal bot.
    handler = partial(
        _Handler,
        database_path=database_path,
        make_lead_service=make_lead_service,
        hunt_lock=threading.Lock(),
    )
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"kantor 3D siap di http://127.0.0.1:{port}  (Ctrl+C untuk berhenti)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
