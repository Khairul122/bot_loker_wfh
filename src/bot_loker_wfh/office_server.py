"""Serve the 3D office view with live counts from the local database."""

from __future__ import annotations

import json
import re
import queue
import shlex
from .database import Connection
import subprocess
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from . import office_desk as desk
from . import database
from .employee_skills import all_employee_skills, load_employee_skills
from .github_portfolio import USERNAME_RE, load_portfolio, sync_portfolio
from .lead_desk import RevisionFailed
from .office_work import open_db
from .office_state import load_state, save_state
from .office_events import bus as office_events
from .settings_store import DEFAULTS, all_settings, get_setting, set_setting
from .config import save_dotenv
from .status_transitions import InvalidTransitionError

OFFICE_DIR = Path(__file__).with_name("office")
HUNT_RESULT_LIMIT = 5

# Settings the office panel may persist. Anything else is rejected.
SECRET_KEYS = frozenset({"ninerouter_api_key"})
ALLOWED_SETTINGS = frozenset({
    "llm_provider",
    "ninerouter_base_url", "ninerouter_api_key", "ninerouter_model",
    "ninerouter_fallback_models", "llm_model_draft", "llm_model_form",
    "llm_model_answer", "llm_timeout_seconds", "llm_task_budget_seconds",
    "llm_temperature_draft",
    "browser_mcp_command",
    "form_min_confidence", "form_max_actions", "form_max_tool_calls",
    "form_timeout_seconds", "form_connect_timeout_seconds", "form_ai_answers",
    "applicant_path", "answers_path", "scrape_interval_hours",
})
_NUMERIC_SETTINGS = {
    "llm_timeout_seconds": (1, 3600), "llm_task_budget_seconds": (1, 7200),
    "llm_temperature_draft": (0, 2), "form_min_confidence": (0, 1),
    "form_max_actions": (1, 1000), "form_max_tool_calls": (1, 1000),
    "form_timeout_seconds": (1, 7200), "form_connect_timeout_seconds": (1, 600),
    "scrape_interval_hours": (0.08, 720),
}
_ENUM_SETTINGS = {
    "llm_provider": {"template", "9router"},
    "form_ai_answers": {"review", "off"},
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
        # 9Router Configuration
        "llm_provider": settings.llm_provider,
        "ninerouter_base_url": settings.ninerouter_base_url,
        "ninerouter_api_key": settings.ninerouter_api_key,
        "ninerouter_model": settings.ninerouter_model,
        "ninerouter_fallback_models": ",".join(settings.ninerouter_fallback_models),
        "llm_model_draft": settings.llm_model_draft,
        "llm_model_form": settings.llm_model_form,
        "llm_model_answer": settings.llm_model_answer,
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
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".css": "text/css"}

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
        except database.Error:
            print(f"[office] {self.command} {self.path.split('?')[0]} -> supabase_unavailable", flush=True)
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
            return self._json(200, self._list_9router_models())
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
        origin = self.headers.get("Origin")
        if origin:
            origin_host = origin.split("://", 1)[-1].rstrip("/")
            req_host = (self.headers.get("Host") or "").rstrip("/")
            # Remove port numbers when comparing host origin (e.g. 127.0.0.1:8765 vs localhost)
            def _norm_host(h: str) -> str:
                h_no_port = h.split(":")[0]
                return "127.0.0.1" if h_no_port in ("localhost", "127.0.0.1") else h_no_port
            if _norm_host(origin_host) != _norm_host(req_host):
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
                save_dotenv(values)
            except Exception:
                pass
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
        """Test 9Router LLM connection based on current settings."""
        try:
            from bot_loker_wfh.config import Settings
            from bot_loker_wfh.llm import OpenAICompatibleProvider, LLMError
            
            settings = Settings.from_environment()
            prov = OpenAICompatibleProvider(
                settings.ninerouter_base_url,
                settings.ninerouter_api_key or "sk-dummy",
                settings.ninerouter_model or "LokerHouse",
            )
            models = prov.list_models()
            test_res = prov.complete([{"role": "user", "content": "Tes satu kata."}])
            return {"ok": True, "message": f"9Router terhubung. {len(models)} model tersedia. Model test: {test_res.model}", "model": test_res.model}
        except LLMError as err:
            if err.code == "unauthorized":
                return {"ok": False, "error": "API key ditolak (401)"}
            return {"ok": False, "error": str(err)}
        except Exception as err:
            return {"ok": False, "error": f"Koneksi gagal: {err}"}

    def _list_9router_models(self):
        """List all models from 9Router."""
        try:
            from bot_loker_wfh.config import Settings
            from bot_loker_wfh.llm import fetch_9router_models_categorized
            
            settings = Settings.from_environment()
            result = fetch_9router_models_categorized(
                settings.ninerouter_base_url,
                settings.ninerouter_api_key or "sk-dummy",
            )
            return result
        except Exception as err:
            return {"combo": [], "vision": [], "all": [], "error": str(err)}

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
