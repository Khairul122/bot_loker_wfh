"""Serve the 3D office view with live counts from the local database."""

from __future__ import annotations

import json
import re
import queue
import shlex
from .database import Connection
import subprocess
import time
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from . import office_desk as desk
from . import database
from .employee_skills import all_employee_skills, load_employee_skills
from .github_portfolio import USERNAME_RE, load_portfolio, sync_portfolio
from .auto_bid import AUTO_BID_KEYS
from .lead_desk import RevisionFailed
from .office_work import open_db
from .office_state import load_state, save_state
from .office_events import bus as office_events
from .settings_store import DEFAULTS, all_settings, get_setting, set_setting
from .config import save_dotenv
from .status_transitions import InvalidTransitionError

OFFICE_DIR = Path(__file__).with_name("office")
HUNT_RESULT_LIMIT = 5
_INSTINCT_COOLDOWN = 90.0  # seconds between LLM instinct calls per employee (cost cap)
_INSTINCT_LAST: dict[str, float] = {}

# Settings the office panel may persist. Anything else is rejected.
SECRET_KEYS = frozenset({"hermes_api_key"})
ALLOWED_SETTINGS = frozenset({
    "llm_provider",
    "hermes_base_url", "hermes_api_key", "hermes_model_draft",
    "hermes_model_form", "hermes_model_answer", "llm_timeout_seconds", "llm_task_budget_seconds",
    "llm_temperature_draft",
    "browser_mcp_command",
    "form_min_confidence", "form_max_actions", "form_max_tool_calls",
    "form_timeout_seconds", "form_connect_timeout_seconds", "form_ai_answers",
    "applicant_path", "answers_path", "scrape_interval_hours",
    "auto_bid_enabled", "auto_bid_max_per_day", "auto_bid_min_score", "auto_bid_max_competitors", "auto_bid_max_age_hours",
})
_NUMERIC_SETTINGS = {
    "llm_timeout_seconds": (1, 3600), "llm_task_budget_seconds": (1, 7200),
    "llm_temperature_draft": (0, 2), "form_min_confidence": (0, 1),
    "form_max_actions": (1, 1000), "form_max_tool_calls": (1, 1000),
    "form_timeout_seconds": (1, 7200), "form_connect_timeout_seconds": (1, 600),
    "scrape_interval_hours": (0.08, 720),
    "auto_bid_max_per_day": (1, 50), "auto_bid_min_score": (0, 1),
    "auto_bid_max_competitors": (1, 500), "auto_bid_max_age_hours": (1, 720),
}
_ENUM_SETTINGS = {
    "llm_provider": {"template", "hermes"},
    "form_ai_answers": {"review", "off"},
    "auto_bid_enabled": {"0", "1"},
}
_ENV_SETTINGS_KEYS = {
    "llm_provider": "LLM_PROVIDER",
    "hermes_base_url": "HERMES_BASE_URL",
    "hermes_api_key": "HERMES_API_KEY",
    "hermes_model_draft": "HERMES_MODEL_DRAFT",
    "hermes_model_form": "HERMES_MODEL_FORM",
    "hermes_model_answer": "HERMES_MODEL_ANSWER",
    "llm_timeout_seconds": "LLM_TIMEOUT_SECONDS",
    "llm_task_budget_seconds": "LLM_TASK_BUDGET_SECONDS",
    "llm_temperature_draft": "LLM_TEMPERATURE_DRAFT",
    "browser_mcp_command": "BROWSER_MCP_COMMAND",
    "form_min_confidence": "FORM_MIN_CONFIDENCE",
    "form_max_actions": "FORM_MAX_ACTIONS",
    "form_max_tool_calls": "FORM_MAX_TOOL_CALLS",
    "form_timeout_seconds": "FORM_TIMEOUT_SECONDS",
    "form_connect_timeout_seconds": "FORM_CONNECT_TIMEOUT_SECONDS",
    "form_ai_answers": "FORM_AI_ANSWERS",
    "applicant_path": "APPLICANT_PATH",
    "answers_path": "ANSWERS_PATH",
}


def _mask(secret: str | None) -> dict:
    """Never hand the raw secret to the browser; show only a set flag and last 4."""
    if not secret:
        return {"value": "", "set": False}
    tail = secret[-4:] if len(secret) > 4 else ""
    return {"value": "", "set": True, "hint": f"••••{tail}" if tail else "••••"}


def _validate_setting(key: str, value: str) -> str | None:
    """Return an error message for a bad value, or None when acceptable."""
    if key in _ENUM_SETTINGS:
        return None if value in _ENUM_SETTINGS[key] else f"{key} tidak valid"
    if key in _NUMERIC_SETTINGS:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return f"{key} harus berupa angka"
        low, high = _NUMERIC_SETTINGS[key]
        return None if low <= number <= high else f"{key} di luar rentang {low}-{high}"
    return None


_PREF_KEYS = ("look", "sound", "auto", "freelancer", "linkedin", "github")
_LOOK_FIELDS = ("name", "skin", "hair", "shirt", "pants")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _browser_request_is_local(headers, server_port: int) -> bool:
    """Reject browser requests that can reach loopback through DNS rebinding."""
    request_url = urlsplit(f"//{headers.get('Host') or ''}")
    if request_url.hostname not in _LOOPBACK_HOSTS:
        return False
    try:
        if request_url.port not in (None, server_port):
            return False
    except ValueError:
        return False

    origin = headers.get("Origin")
    if not origin:
        return True
    origin_url = urlsplit(origin)
    if origin_url.scheme != "http" or origin_url.hostname not in _LOOPBACK_HOSTS:
        return False
    try:
        return origin_url.port == server_port
    except ValueError:
        return False


def _validate_pref(key: str, value: str) -> str | None:
    """The owner's UI preferences (character look, sound, auto mode) kept in Supabase."""
    if key not in _PREF_KEYS:
        return "unknown_pref"
    if key in ("sound", "auto"):
        return None if value in ("0", "1") else "invalid_value"
    if key in ("freelancer", "linkedin"):
        return None if value == "" or (len(value) <= 300 and re.match(r"^https://[^\s]+$", value)) else "invalid_url"
    if key == "github":
        return None if value == "" or USERNAME_RE.match(value) else "invalid_username"
    try:
        look = json.loads(value)
    except ValueError:
        return "invalid_value"
    if not isinstance(look, dict) or not set(look) <= set(_LOOK_FIELDS):
        return "invalid_value"
    name = look.get("name", "Owner")
    if not isinstance(name, str) or not 1 <= len(name) <= 14:
        return "invalid_value"
    if any(not (isinstance(look.get(f), str) and _HEX.match(look[f])) for f in _LOOK_FIELDS[1:] if f in look):
        return "invalid_value"
    return None


def _grouped(connection: Connection, sql: str) -> dict:
    rows = connection.execute(sql).fetchall()
    out: dict = {}
    for *keys, count in rows:
        node = out
        for key in keys[:-1]:
            node = node.setdefault(key, {})
        node[keys[-1]] = count
    return out


def collect_stats(connection: Connection) -> dict:
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


def _settings_payload(connection: Connection) -> dict:
    """Current runtime-tunable settings (interval in hours, min bound for the UI)."""
    payload = {
        key: {"value": get_setting(connection, key), "min": lower}
        for key, (_, lower) in DEFAULTS.items()
    }
    return payload


def _all_settings_payload(overrides: dict[str, str] | None = None) -> dict:
    """All settings including from environment/config for the settings panel.

    `overrides` (the stored `app_settings` rows) win over the environment. Secrets stay
    masked regardless of where they came from.
    """
    from bot_loker_wfh.config import Settings
    settings = Settings.from_environment()
    
    # All settings that the panel needs
    all_settings = {
        # Hermes Agent configuration
        "llm_provider": settings.llm_provider,
        "hermes_base_url": settings.hermes_base_url,
        "hermes_api_key": settings.hermes_api_key,
        "hermes_model_draft": settings.hermes_model_draft,
        "hermes_model_form": settings.hermes_model_form,
        "hermes_model_answer": settings.hermes_model_answer,
        "llm_timeout_seconds": settings.llm_timeout_seconds,
        "llm_task_budget_seconds": settings.llm_task_budget_seconds,
        "llm_temperature_draft": settings.llm_temperature_draft,
        
        # Form Engine
        "browser_mcp_command": settings.browser_mcp_command,
        "form_min_confidence": settings.form_min_confidence,
        "form_max_actions": settings.form_max_actions,
        "form_max_tool_calls": settings.form_max_tool_calls,
        "form_timeout_seconds": settings.form_timeout_seconds,
        "form_connect_timeout_seconds": settings.form_connect_timeout_seconds,
        "form_ai_answers": settings.form_ai_answers,
        
        # Data paths
        "applicant_path": settings.applicant_path,
        "answers_path": settings.answers_path,
    }

    for key in AUTO_BID_KEYS:  # stored in Supabase only; show the default until the owner changes it
        all_settings[key] = DEFAULTS[key][0]
    payload = {k: (_mask(v) if k in SECRET_KEYS else {"value": v}) for k, v in all_settings.items()}
    if overrides:
        # Stored values win: real secret values mark "set"
        # and never leak, everything else shows the stored value.
        for key, value in overrides.items():
            if key in SECRET_KEYS:
                payload[key] = _mask(value if value else None)
            elif key in payload:
                payload[key] = {"value": value}
    return payload


def hunt_leads(connection: Connection, lead_service, source: str) -> dict:
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


def hunt_jobs(connection: Connection, source: str, fetcher, pipeline) -> dict:
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
    "bid": (
        "SELECT title, COALESCE(budget, '') || ' · ' || source, url, status, score, fetched_at, kind "
        "FROM leads WHERE proposal IS NOT NULL ORDER BY fetched_at DESC LIMIT ?"
    ),
}


def employee_results(connection: Connection, view: str, source: str | None = None) -> list[dict]:
    """Recent output of one kind of work, for the owner to review (never CV content)."""
    sql = _RESULT_QUERIES.get(view)
    if sql is None:
        return []
    params = (source, RESULT_LIMIT) if view in ("jobs", "leads") else (RESULT_LIMIT,)
    if view == "bid":
        params = (RESULT_LIMIT,)
    keys = ("title", "sub", "url", "tag", "score", "when", "detail")
    return [dict(zip(keys, row)) for row in connection.execute(sql, params).fetchall()]


def desk_state(connection: Connection) -> dict:
    """What the 3D owner's office needs on every poll: ratings, instructions, reports to walk over."""
    return {
        "ratings": desk.ratings(connection),
        "instructions": desk.instructions(connection),
        "undelivered": desk.undelivered(connection),
        "tray": desk.tray_count(connection),
    }


class _Handler(SimpleHTTPRequestHandler):
    # the Windows registry can map .js to text/plain, which browsers refuse for ES modules
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".css": "text/css",
        ".glb": "model/gltf-binary",
        ".gltf": "model/gltf+json",
    }

    def __init__(self, *args, work, **kwargs):
        self.work = work
        super().__init__(*args, directory=str(OFFICE_DIR), **kwargs)

    def end_headers(self):
        # never let the browser cache a stale module: a cached sync.js without a new export breaks boot
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)
        return True  # lets route helpers signal "handled"

    def _connect(self):
        return open_db()

    def _guarded(self, handler) -> None:
        """A failing request answers 503/500 instead of silently closing the socket
        (the browser shows that as ERR_CONNECTION_CLOSED)."""
        try:
            handler()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # the page went away mid-answer
        except database.Error as error:
            # class name + SQLSTATE only: provider error text may carry credentials or data
            detail = f"{type(error).__name__} {getattr(error, 'sqlstate', None) or ''}".strip()
            print(f"[office] {self.command} {self.path.split('?')[0]} -> supabase_unavailable ({detail})", flush=True)
            self._safe_error(503, "supabase_unavailable")
        except Exception as error:
            print(f"[office] {self.command} {self.path.split('?')[0]} -> {type(error).__name__}", flush=True)
            self._safe_error(500, "server_error")

    def _safe_error(self, status: int, code: str) -> None:
        try:
            self._json(status, {"error": code})
        except Exception:
            pass  # headers already sent or socket gone

    def do_GET(self):
        self._guarded(self._get)

    def do_POST(self):
        self._guarded(self._post)

    def _get(self):
        path = self.path.split("?")[0]
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if path in ("/ws/logs", "/ws"):
            if not _browser_request_is_local(self.headers, self.server.server_address[1]):
                return self._json(403, {"error": "forbidden"})
            ws_key = self.headers.get("Sec-WebSocket-Key")
            if not ws_key:
                self.send_error(400, "Missing Sec-WebSocket-Key")
                return
            import base64, hashlib
            magic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
            accept_key = base64.b64encode(hashlib.sha1((ws_key + magic).encode()).digest()).decode()
            self.send_response(101, "Switching Protocols")
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", accept_key)
            self.end_headers()

            def send_ws_frame(msg_bytes: bytes):
                length = len(msg_bytes)
                if length <= 125:
                    header = bytes([0x81, length])
                elif length <= 65535:
                    header = bytes([0x81, 126]) + length.to_bytes(2, "big")
                else:
                    header = bytes([0x81, 127]) + length.to_bytes(8, "big")
                self.wfile.write(header + msg_bytes)
                self.wfile.flush()

            subscription = office_events.subscribe()
            try:
                while True:
                    try:
                        event = subscription.get(timeout=5)
                        send_ws_frame(json.dumps(event).encode("utf-8"))
                    except queue.Empty:
                        try:
                            with self._connect() as connection:
                                snapshot = {**collect_stats(connection), "work": self.work.status(),
                                            "desk": desk_state(connection)}
                            send_ws_frame(json.dumps({"type": "stats", "data": snapshot}).encode("utf-8"))
                        except Exception:
                            self.wfile.write(bytes([0x89, 0x00]))
                            self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                subscription.close()
            return
        if path == "/events":
            subscription = office_events.subscribe()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                while True:
                    try:
                        event = subscription.get(timeout=15)
                        self.wfile.write(f"data: {json.dumps(event)}\\n\\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": keep-alive\\n\\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                subscription.close()
            return
        if path == "/office/state.json":
            with self._connect() as connection:
                return self._json(200, load_state(connection))
        if path == "/stats.json":
            with self._connect() as connection:
                return self._json(200, {**collect_stats(connection), "work": self.work.status(),
                                        "desk": desk_state(connection)})
        if path == "/employee.json":
            employee = parse_qs(urlsplit(self.path).query).get("id", [""])[0]
            with self._connect() as connection:
                try:
                    return self._json(200, desk.profile(connection, employee))
                except KeyError:
                    return self._json(404, {"error": "not_found"})
        if path == "/manager/tasks.json":
            manager = parse_qs(urlsplit(self.path).query).get("id", [""])[0]
            from .manager_tasks import list_tasks
            try:
                with self._connect() as connection:
                    return self._json(200, {"items": list_tasks(connection, manager)})
            except KeyError:
                return self._json(404, {"error": "not_manager"})
        if path == "/employee-memory.json":
            employee = parse_qs(urlsplit(self.path).query).get("id", [""])[0]
            if employee not in desk.ROLES:
                return self._json(404, {"error": "not_found"})
            with self._connect() as connection:
                from .employee_memory import list_memories
                return self._json(200, {"id": employee, "items": list_memories(connection, employee, limit=10)})
        if path == "/observability.json":
            if not _browser_request_is_local(self.headers, self.server.server_address[1]):
                return self._json(403, {"error": "forbidden"})
            query = parse_qs(urlsplit(self.path).query)
            try:
                hours = int(query.get("hours", ["24"])[0])
            except (TypeError, ValueError):
                return self._json(400, {"error": "invalid_period"})
            if hours not in (0, 4, 24, 168):
                return self._json(400, {"error": "invalid_period"})
            cutoff = None if hours == 0 else (
                datetime.now(timezone.utc) - timedelta(hours=hours)
            ).isoformat(timespec="seconds").replace("+00:00", "Z")
            with self._connect() as connection:
                if cutoff is None:
                    memory_rows = connection.execute(
                        "SELECT id, employee_id, kind, content, importance, created_at "
                        "FROM employee_memory ORDER BY created_at DESC LIMIT 1000"
                    ).fetchall()
                    event_rows = connection.execute(
                        "SELECT me.id, me.meeting_id, me.employee_id, me.event_type, me.content, "
                        "me.created_at, m.title FROM meeting_events me "
                        "JOIN meetings m ON me.meeting_id = m.id "
                        "ORDER BY me.created_at DESC LIMIT 1000"
                    ).fetchall()
                    chat_rows = connection.execute(
                        "SELECT id, conversation_id, employee_id, speaker, channel, content, created_at "
                        "FROM employee_conversations ORDER BY created_at DESC LIMIT 1000"
                    ).fetchall()
                    report_rows = connection.execute(
                        "SELECT employee, score, rating, created_at FROM office_reports "
                        "ORDER BY created_at DESC LIMIT 1000"
                    ).fetchall()
                else:
                    memory_rows = connection.execute(
                        "SELECT id, employee_id, kind, content, importance, created_at "
                        "FROM employee_memory WHERE created_at >= ? "
                        "ORDER BY created_at DESC LIMIT 1000", (cutoff,)
                    ).fetchall()
                    event_rows = connection.execute(
                        "SELECT me.id, me.meeting_id, me.employee_id, me.event_type, me.content, "
                        "me.created_at, m.title FROM meeting_events me "
                        "JOIN meetings m ON me.meeting_id = m.id WHERE me.created_at >= ? "
                        "ORDER BY me.created_at DESC LIMIT 1000", (cutoff,)
                    ).fetchall()
                    chat_rows = connection.execute(
                        "SELECT id, conversation_id, employee_id, speaker, channel, content, created_at "
                        "FROM employee_conversations WHERE created_at >= ? "
                        "ORDER BY created_at DESC LIMIT 1000", (cutoff,)
                    ).fetchall()
                    report_rows = connection.execute(
                        "SELECT employee, score, rating, created_at FROM office_reports "
                        "WHERE created_at >= ? ORDER BY created_at DESC LIMIT 1000", (cutoff,)
                    ).fetchall()
            performance = {}
            for employee, score, rating, created_at in report_rows:
                item = performance.setdefault(employee, {"employee": employee, "reports": 0,
                                                         "score_total": 0.0, "rating_total": 0,
                                                         "rated_reports": 0, "latest_at": created_at})
                item["reports"] += 1
                item["score_total"] += float(score)
                if rating is not None:
                    item["rating_total"] += int(rating)
                    item["rated_reports"] += 1
            performance = [
                {"employee": item["employee"], "reports": item["reports"],
                 "avg_score": round(item["score_total"] / item["reports"], 2),
                 "avg_rating": round(item["rating_total"] / item["rated_reports"], 2)
                 if item["rated_reports"] else None,
                 "rated_reports": item["rated_reports"], "latest_at": item["latest_at"]}
                for item in performance.values()
            ]
            conversations = [
                {"id": row[0], "conversation_id": row[1], "employee_id": row[2],
                 "speaker": row[3], "channel": row[4], "content": row[5],
                 "created_at": row[6], "title": "Tanya jawab web"}
                for row in chat_rows
            ]
            conversations.extend(
                {"id": row[0], "meeting_id": row[1], "conversation_id": row[1], "employee_id": row[2],
                 "speaker": "employee", "channel": "meeting", "content": row[4],
                 "created_at": row[5], "title": row[6], "event_type": row[3]}
                for row in event_rows
            )
            conversations.sort(key=lambda item: item["created_at"], reverse=True)
            return self._json(200, {
                "hours": hours,
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                "memories": [dict(zip(("id", "employee_id", "kind", "content", "importance", "created_at"), row))
                             for row in memory_rows],
                "conversations": conversations[:1000],
                "performance": performance,
                "truncated": len(memory_rows) == 1000 or len(event_rows) == 1000 or
                             len(chat_rows) == 1000 or len(report_rows) == 1000,
            })
        if path == "/employee-skills.json":
            try:
                return self._json(200, {"employees": all_employee_skills()})
            except (KeyError, ValueError):
                return self._json(500, {"error": "employee_skills_unavailable"})
        if path == "/employee-skills":
            employee = parse_qs(urlsplit(self.path).query).get("id", [""])[0]
            try:
                return self._json(200, {"id": employee, "markdown": load_employee_skills(employee)})
            except KeyError:
                return self._json(404, {"error": "not_found"})
            except ValueError:
                return self._json(413, {"error": "employee_skills_invalid"})
        if path == "/reports.json":
            employee = parse_qs(urlsplit(self.path).query).get("employee", [None])[0]
            with self._connect() as connection:
                return self._json(200, {"items": desk.list_reports(connection, employee),
                                        "ratings": desk.ratings(connection),
                                        "telegram": self.work.notify is not None})
        if path == "/results.json":
            query = parse_qs(urlsplit(self.path).query)
            view, source = query.get("view", [""])[0], query.get("source", [None])[0]
            with self._connect() as connection:
                return self._json(200, {"items": employee_results(connection, view, source)})
        if path == "/github.json":
            with self._connect() as connection:
                data = load_portfolio(connection)
            return self._json(200, {"username": data.get("username"), "synced_at": data.get("synced_at"),
                                    "repos": len(data.get("repos", []))})
        if path == "/leads.json":
            query = parse_qs(urlsplit(self.path).query)
            source, view = query.get("source", [None])[0], query.get("view", ["all"])[0]
            with self._connect() as connection:
                return self._json(200, self.work.leads(connection, source, view))
        if path == "/inbox.json":
            with self._connect() as connection:
                return self._json(200, self.work.inbox(connection))
        if path == "/office/prefs.json":
            with self._connect() as connection:
                stored = all_settings(connection)
            return self._json(200, {k: stored[f"ui_{k}"] for k in _PREF_KEYS if f"ui_{k}" in stored})
        if path == "/settings.json":
            with self._connect() as connection:
                return self._json(200, _all_settings_payload(all_settings(connection)))
        if path == "/llm/test":
            return self._json(200, self._test_llm())
        if path == "/llm/list-models":
            return self._json(200, self._list_hermes_models())
        if path == "/browser/test":
            return self._json(200, self._test_browser())
        if path == "/ats/list":
            with self._connect() as connection:
                return self._json(200, {"ats": self._list_ats(connection)})
        return super().do_GET()

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        return body if isinstance(body, dict) else {}

    def _post(self):
        # Other sites open in the browser must not trigger actions on the owner's machine.
        if not _browser_request_is_local(self.headers, self.server.server_address[1]):
            return self._json(403, {"error": "forbidden"})
        parts = self.path.strip("/").split("/")
        if parts == ["office", "character-state"]:
            try:
                with self._connect() as connection:
                    return self._json(200, save_state(connection, self._body()))
            except (TypeError, ValueError):
                return self._json(400, {"error": "invalid"})
        if parts in (["meetings", "run"], ["api", "meetings", "run"]):
            body = self._body()
            topic = str(body.get("topic") or "Strategi Rekrutmen dan Lamaran").strip()
            participants = body.get("participants") or ["cora", "tegar", "reno"]
            with self._connect() as connection:
                from .meeting_runtime import run_dynamic_meeting
                result = run_dynamic_meeting(connection, topic, participants)
            for line in result.get("transcript", []):
                office_events.publish({"employee": line.get("employee"), "task": topic, "status": "rapat"})
            office_events.publish({"employee": "owner", "task": topic, "status": "keputusan"})
            return self._json(200, result)
        if parts == ["api", "staff-instinct"]:
            body = self._body()
            employee = str(body.get("id") or "")
            if employee not in desk.ROLES:
                return self._json(400, {"error": "invalid"})
            now = time.monotonic()
            if now -_INSTINCT_LAST.get(employee, -_INSTINCT_COOLDOWN) < _INSTINCT_COOLDOWN:
                return self._json(429, {"error": "cooldown"})  # the page falls back to its local instinct
            _INSTINCT_LAST[employee] = now
            with self._connect() as connection:
                decision = desk.instinct(connection, self.work.llm, employee, body)
            return self._json(200, decision) if decision else self._json(503, {"error": "unavailable"})
        handled = self._desk_post(parts)
        if handled is not None:
            return handled
        if parts == ["github", "sync"]:
            username = str(self._body().get("username") or "").strip()
            try:
                with self._connect() as connection:
                    username = username or get_setting(connection, "ui_github")
                    data = sync_portfolio(username, connection)
            except ValueError:
                return self._json(400, {"error": "invalid_username"})
            except HTTPError as error:
                if error.code == 404:
                    return self._json(404, {"error": "github_user_not_found"})
                return self._json(502, {"error": "github_unreachable"})
            except OSError:
                return self._json(502, {"error": "github_unreachable"})
            except database.Error:
                return self._json(503, {"error": "supabase_unavailable"})
            return self._json(200, {"username": username, "synced_at": data["synced_at"], "repos": len(data["repos"])})
        if parts == ["auto"]:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            self.work.set_auto(bool(body.get("on")))
            return self._json(200, self.work.status())
        if parts == ["settings"]:
            body = self._body()
            values = body.get("values") if isinstance(body.get("values"), dict) else {str(body.get("key") or ""): str(body.get("value") or "")}
            values = {str(k): str(v if v is not None else "").strip() for k, v in values.items()}
            for key, value in values.items():
                if key not in ALLOWED_SETTINGS:
                    return self._json(400, {"error": "unknown_setting", "key": key})
                error = _validate_setting(key, value)
                if error:
                    return self._json(400, {"error": error, "key": key})
            # a blank secret means "keep the stored one", never wipe it
            values = {k: v for k, v in values.items() if not (k in SECRET_KEYS and v == "")}
            try:
                with self._connect() as connection:
                    for key, value in values.items():
                        set_setting(connection, key, value)
                    payload = _all_settings_payload(all_settings(connection))
            except database.Error:
                # Success is only reported once the values are stored in Supabase.
                return self._json(503, {"error": "supabase_unavailable"})
            try:  # persist to .env so it survives a restart (best effort)
                save_dotenv({_ENV_SETTINGS_KEYS.get(key, key): value for key, value in values.items()})
            except Exception:
                pass
            if values.get("auto_bid_enabled") == "1" and self.work.auto:
                self.work.run_soon()  # switching auto-bid on starts a round right away, not hours later
            return self._json(200, payload)
        if parts == ["office", "prefs"]:
            body = self._body()
            key, value = str(body.get("key") or ""), str(body.get("value") if body.get("value") is not None else "")
            error = _validate_pref(key, value)
            if error:
                return self._json(400, {"error": error})
            try:
                with self._connect() as connection:
                    set_setting(connection, f"ui_{key}", value)
            except database.Error:
                return self._json(503, {"error": "supabase_unavailable"})
            return self._json(200, {"ok": True})
        if len(parts) == 3 and parts[0] == "leads":
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            try:
                with self._connect() as connection:
                    return self._json(200, self.work.lead_action(connection, parts[1], parts[2], body))
            except KeyError:
                return self._json(404, {"error": "not_found"})
            except RevisionFailed as error:
                return self._json(502, {"error": "llm_unavailable", "message": str(error)})
            except ValueError as error:
                message = str(error)  # user-safe reasons written in lead_desk / office_work
                return self._json(404 if message.startswith("unknown action") else 400, {"error": message})
        if len(parts) == 3 and parts[0] == "inbox":
            try:
                with self._connect() as connection:
                    return self._json(200, self.work.decide(connection, parts[1], parts[2]))
            except InvalidTransitionError:
                return self._json(409, {"error": "stale"})
        if len(parts) == 2 and parts[0] == "hunt" and parts[1] in self.work.hunters:
            hunter, owner = self.work.hunters[parts[1]], desk.SOURCE_OWNER.get(parts[1])
            action = {"task": "hunt", "employee": owner, "source": parts[1]}

            def job(connection, hunter=hunter, owner=owner):
                result = hunter(connection)
                if owner:  # the scout's standing instruction decides which finds are shown first
                    words = desk.keywords(desk.get_instruction(connection, owner))
                    result["top"] = desk.prioritize(result.get("top", []), words)
                return result
        elif parts == ["work", "screen"] and self.work.screener is not None:
            action = {"task": "screen", "employee": "sari"}
            job = self.work.screener
        elif parts == ["inbox", "draft"]:
            # draft_next logs its own success line; the handler only adds failures
            action = {"task": None, "employee": "cora"}
            job = lambda connection: {"drafted": self.work.draft_next(connection)}  # noqa: E731
        else:
            return self._json(404, {"error": "not_found"})
        if not self.work.lock.acquire(blocking=False):
            return self._json(409, {"error": "busy"})
        started = time.perf_counter()
        try:
            with self._connect() as connection:
                result = job(connection)
            if action["task"] is not None:
                duration = int((time.perf_counter() - started) * 1000)
                self.work.log_work(
                    action["employee"], action["task"], source=action.get("source"),
                    matched=result.get("matched"), inserted_count=result.get("inserted"),
                    count=result.get("drafted"), duration_ms=duration,
                )
                if action["task"] == "screen" and result.get("filtered_out") is not None:
                    # Eli throws the ineligible ones out; Sari scores what survived
                    self.work.log_work("eli", "screen", count=result["filtered_out"], duration_ms=duration)
            self._json(200, result)
        except Exception as error:  # surfaced to the page as a sad employee, not a stack trace
            self.work.log_failure(
                action["employee"], action["task"], error, source=action.get("source"),
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            self._json(502, {"error": type(error).__name__})
        finally:
            self.work.lock.release()

    def _desk_post(self, parts: list[str]):
        """Owner's office routes; None when the path is not one of them."""
        try:
            if parts == ["manager", "brief"]:
                from .manager_tasks import assign_recommendations, division_brief
                manager = str(self._body().get("manager") or "")
                try:
                    with self._connect() as connection:
                        brief = division_brief(connection, manager, self.work.llm)
                        brief["assigned_tasks"] = assign_recommendations(
                            connection, manager, brief["priorities"]
                        )
                except KeyError:
                    return self._json(404, {"error": "not_manager"})
                except RuntimeError:
                    return self._json(503, {"error": "hermes_unavailable"})
                except ValueError:
                    return self._json(502, {"error": "invalid_manager_brief"})
                self.work.log_work(manager, "division_brief", division=brief["division"]["id"],
                                   assignments=len(brief["assigned_tasks"]))
                for task in brief["assigned_tasks"]:
                    office_events.publish({"employee": task["assignee"], "task": task["title"],
                                           "status": "ditugaskan"})
                office_events.publish({"employee": manager, "task": "brief divisi", "status": "selesai"})
                return self._json(200, brief)
            if parts == ["manager", "tasks"]:
                from .manager_tasks import create_task
                body = self._body()
                try:
                    with self._connect() as connection:
                        task = create_task(connection, str(body.get("manager") or ""),
                                           str(body.get("assignee") or ""), str(body.get("title") or ""),
                                           str(body.get("priority") or "normal"))
                except KeyError:
                    return self._json(404, {"error": "not_manager"})
                except ValueError as error:
                    return self._json(400, {"error": str(error)})
                office_events.publish({"employee": task["assignee"], "task": task["title"], "status": "ditugaskan"})
                return self._json(201, task)
            if len(parts) == 3 and parts[:2] == ["manager", "tasks"]:
                from .manager_tasks import update_task
                body = self._body()
                try:
                    with self._connect() as connection:
                        task = update_task(connection, str(body.get("manager") or ""), parts[2],
                                           str(body.get("status") or ""), str(body.get("review_note") or ""))
                except KeyError:
                    return self._json(404, {"error": "not_found"})
                except ValueError as error:
                    return self._json(400, {"error": str(error)})
                office_events.publish({"employee": task["assignee"], "task": task["title"], "status": task["status"]})
                return self._json(200, task)
            if len(parts) == 3 and parts[:2] == ["reports", "request"]:
                with self._connect() as connection:
                    return self._json(200, self.work.request_reports(connection, parts[2]))
            if len(parts) == 3 and parts[0] == "reports" and parts[2] == "delivered":
                with self._connect() as connection:
                    desk.mark_delivered(connection, parts[1])
                    return self._json(200, {"ok": True})
            if len(parts) == 3 and parts[0] == "reports" and parts[2] == "review":
                body = self._body()
                with self._connect() as connection:
                    report = desk.review_report(connection, parts[1], body.get("rating"), str(body.get("note") or ""))
                    self.work.log_work(report["employee"], "review", rating=report["rating"])
                    return self._json(200, report)
            if len(parts) == 2 and parts[0] == "instructions":
                text = str(self._body().get("text") or "")
                with self._connect() as connection:
                    saved = desk.set_instruction(connection, parts[1], text)
                    self.work.log_work(parts[1], "instruction", count=len(text))
                    return self._json(200, {"text": saved})
            if len(parts) == 2 and parts[0] == "ask":
                question = str(self._body().get("question") or "")
                with self._connect() as connection:
                    answer = desk.ask(connection, self.work.llm, parts[1], question)
                    from .employee_conversations import record_web_exchange
                    record_web_exchange(connection, parts[1], question, answer.get("answer", ""))
                    self.work.log_work(parts[1], "question", mode="ai" if answer.get("ai") else "facts")
                    return self._json(200, answer)
            if parts == ["work", "telegram"]:
                with self._connect() as connection:
                    return self._json(200, self.work.telegram_digest(connection))
        except KeyError:
            return self._json(404, {"error": "not_found"})
        except (TypeError, ValueError):
            return self._json(400, {"error": "invalid"})
        except (OSError, RuntimeError):  # Telegram / LLM unreachable
            return self._json(502, {"error": "unreachable"})
        return None

    def _test_llm(self):
        """Check Hermes gateway readiness without spending a model request."""
        try:
            from bot_loker_wfh.config import Settings
            from bot_loker_wfh.llm import HermesAgentClient
            
            settings = Settings.from_environment()
            client = HermesAgentClient(
                settings.hermes_base_url,
                settings.hermes_api_key,
                settings.hermes_model_draft,
                timeout=settings.llm_timeout_seconds,
            )
            aliases = (
                settings.hermes_model_draft,
                settings.hermes_model_form,
                settings.hermes_model_answer,
            )
            readiness = client.check_readiness(required_models=aliases)
            actual = set(readiness.get("toolsets") or [])
            ready = readiness.get("ok")
            return {
                "ok": bool(ready),
                "status": readiness.get("status", "unknown"),
                "version": readiness.get("version", ""),
                "toolsets": sorted(actual),
                "models": readiness.get("models", []),
                "error": None if ready else "Periksa gateway, model aliases, dan allowlist skills/memory/delegation",
            }
        except (ValueError, OSError, RuntimeError):
            return {"ok": False, "status": "misconfigured", "toolsets": [], "error": "Hermes configuration is invalid"}

    def _list_hermes_models(self):
        """List model aliases advertised by Hermes; provider inventory stays in Hermes."""
        try:
            from bot_loker_wfh.config import Settings
            from bot_loker_wfh.llm import HermesAgentClient
            
            settings = Settings.from_environment()
            models = HermesAgentClient(
                settings.hermes_base_url,
                settings.hermes_api_key,
                timeout=settings.llm_timeout_seconds,
            ).list_models()
            return {"models": models, "error": None}
        except Exception:
            return {"models": [], "error": "Hermes API Server is unavailable or misconfigured"}

    def _test_browser(self):
        """Test BrowserMCP connection."""
        try:
            from bot_loker_wfh.config import Settings
            from bot_loker_wfh.browser_mcp import McpBrowserClient, McpNotConnectedError
            
            settings = Settings.from_environment()
            client = McpBrowserClient(command=settings.browser_mcp_command)
            client.start()
            try:
                client.wait_for_extension(timeout=15.0)
                client.stop()
                return {"ok": True, "message": "BrowserMCP terhubung dan ekstensi Connect"}
            except McpNotConnectedError:
                client.stop()
                return {"ok": False, "error": "Ekstensi BrowserMCP belum Connect. Buka Chrome, klik ikon ekstensi, tekan Connect."}
            except Exception as err:
                client.stop()
                return {"ok": False, "error": str(err)}
        except Exception as err:
            return {"ok": False, "error": f"Gagal start BrowserMCP: {err}"}

    def _list_ats(self, connection):
        """List all ATS registry entries."""
        try:
            rows = connection.execute(
                "SELECT ats_name, host, mode, open_button_label, active, verified_at FROM ats_registry ORDER BY ats_name"
            ).fetchall()
            return [
                {
                    "ats_name": r[0],
                    "host": r[1],
                    "mode": r[2],
                    "open_button_label": r[3],
                    "active": bool(r[4]),
                    "verified_at": r[5],
                }
                for r in rows
            ]
        except Exception:
            return []

    def log_message(self, *args):
        pass


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        import sys
        exctype = sys.exc_info()[0]
        if exctype in (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
            return
        super().handle_error(request, client_address)


def serve(work, port: int = 8765) -> None:
    # Bound to localhost only: the page shows a personal bot's pipeline and cover letters.
    server = QuietThreadingHTTPServer(("127.0.0.1", port), partial(_Handler, work=work))
    work.start_daily_reports()
    work.start_github_sync()
    print(f"kantor 3D siap di http://127.0.0.1:{port}  (Ctrl+C untuk berhenti)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
