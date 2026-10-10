"""Serve the 3D office view with live counts from the local database."""

from __future__ import annotations

import json
import shlex
import sqlite3
import subprocess
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import office_desk as desk
from .github_portfolio import load_portfolio, sync_portfolio
from .office_work import open_db
from .settings_store import DEFAULTS, get_setting, set_setting
from .config import save_dotenv
from .status_transitions import InvalidTransitionError

OFFICE_DIR = Path(__file__).with_name("office")
HUNT_RESULT_LIMIT = 5

# Settings the office panel may persist. Anything else is rejected.
SECRET_KEYS = frozenset({"anthropic_api_key", "ninerouter_api_key"})
ALLOWED_SETTINGS = frozenset({
    "llm_provider", "anthropic_api_key", "anthropic_model",
    "ninerouter_base_url", "ninerouter_api_key", "ninerouter_model",
    "ninerouter_fallback_models", "llm_model_draft", "llm_model_form",
    "llm_model_answer", "llm_timeout_seconds", "llm_task_budget_seconds",
    "llm_temperature_draft", "opencode_command", "opencode_model",
    "form_engine", "browser_mcp_command", "playwright_mcp_command",
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
    "llm_provider": {"template", "anthropic", "9router", "opencode"},
    "form_engine": {"playwright", "browsermcp"},
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
    payload = {
        key: {"value": get_setting(connection, key), "min": lower}
        for key, (_, lower) in DEFAULTS.items()
    }
    return payload


def _all_settings_payload() -> dict:
    """All settings including from environment/config for the settings panel."""
    from bot_loker_wfh.config import Settings
    settings = Settings.from_environment()
    
    # All settings that the panel needs
    all_settings = {
        # LLM Provider
        "llm_provider": settings.llm_provider,
        "anthropic_api_key": settings.anthropic_api_key,
        "anthropic_model": settings.anthropic_model,
        
        # 9Router
        "ninerouter_base_url": settings.ninerouter_base_url,
        "ninerouter_api_key": settings.ninerouter_api_key,
        "ninerouter_model": settings.ninerouter_model,
        "ninerouter_fallback_models": ",".join(settings.ninerouter_fallback_models),
        
        # Per-task models
        "llm_model_draft": settings.llm_model_draft,
        "llm_model_form": settings.llm_model_form,
        "llm_model_answer": settings.llm_model_answer,
        
        # LLM params
        "llm_timeout_seconds": settings.llm_timeout_seconds,
        "llm_task_budget_seconds": settings.llm_task_budget_seconds,
        "llm_temperature_draft": settings.llm_temperature_draft,
        
        # OpenCode
        "opencode_command": settings.opencode_command,
        "opencode_model": settings.opencode_model,
        
        # Form Engine
        "form_engine": settings.form_engine,
        "browser_mcp_command": settings.browser_mcp_command,
        "playwright_mcp_command": settings.playwright_mcp_command,
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
    
    return {
        k: (_mask(v) if k in SECRET_KEYS else {"value": v})
        for k, v in all_settings.items()
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
    "bid": (
        "SELECT title, COALESCE(budget, '') || ' · ' || source, url, status, score, fetched_at, kind "
        "FROM leads WHERE proposal IS NOT NULL ORDER BY fetched_at DESC LIMIT ?"
    ),
}


def employee_results(connection: sqlite3.Connection, view: str, source: str | None = None) -> list[dict]:
    """Recent output of one kind of work, for the owner to review (never CV content)."""
    sql = _RESULT_QUERIES.get(view)
    if sql is None:
        return []
    params = (source, RESULT_LIMIT) if view in ("jobs", "leads") else (RESULT_LIMIT,)
    if view == "bid":
        params = (RESULT_LIMIT,)
    keys = ("title", "sub", "url", "tag", "score", "when", "detail")
    return [dict(zip(keys, row)) for row in connection.execute(sql, params).fetchall()]


def desk_state(connection: sqlite3.Connection) -> dict:
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

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
        return True  # lets route helpers signal "handled"

    def _connect(self):
        return open_db(self.work.database_path)

    def do_GET(self):
        path = self.path.split("?")[0]
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
            data = load_portfolio()
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
        if path == "/settings.json":
            return self._json(200, _all_settings_payload())
        if path == "/llm/test":
            return self._json(200, self._test_llm())
        if path == "/llm/list-models":
            return self._json(200, self._list_9router_models())
        if path == "/browser/test":
            return self._json(200, self._test_browser())
        if path == "/ats/list":
            with self._connect() as connection:
                return self._json(200, {"ats": self._list_ats(connection)})
        if path == "/skills.json":
            return self._json(200, self._get_skills())
        if path == "/form/test":
            engine = parse_qs(urlsplit(self.path).query).get("engine", ["playwright"])[0]
            return self._json(200, self._test_form_engine(engine))
        return super().do_GET()

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        return body if isinstance(body, dict) else {}

    def do_POST(self):
        # Other sites open in the browser must not trigger actions on the owner's machine.
        origin = self.headers.get("Origin")
        if origin and origin.split("://", 1)[-1] != self.headers.get("Host"):
            return self._json(403, {"error": "forbidden"})
        parts = self.path.strip("/").split("/")
        handled = self._desk_post(parts)
        if handled is not None:
            return handled
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
            body = self._body()
            key = str(body.get("key") or "")
            value = str(body.get("value") or "")

            if key not in ALLOWED_SETTINGS:
                return self._json(400, {"error": "unknown_setting"})
            if key in SECRET_KEYS and value == "":
                # Blank secret means "keep the stored one", never wipe it.
                return self._json(200, _all_settings_payload())
            error = _validate_setting(key, value)
            if error:
                return self._json(400, {"error": error})

            if key in DEFAULTS:
                with self._connect() as connection:
                    set_setting(connection, key, value)

            # Persist to .env so it survives a restart (best effort).
            try:
                save_dotenv({key: value})
            except Exception:
                pass

            return self._json(200, _all_settings_payload())
        if parts == ["skills", "reload"]:
            return self._json(200, self._reload_skills())
        if parts == ["skills", "toggle"]:
            body = self._body()
            skill_id = body.get("id")
            enabled = body.get("enabled", True)
            return self._json(200, self._toggle_skill(skill_id, enabled))
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
        """Test LLM connection based on current settings."""
        try:
            from bot_loker_wfh.config import Settings
            from bot_loker_wfh.llm import create_llm_from_settings, OpenAICompatibleProvider, LLMError
            
            settings = Settings.from_environment()
            
            if settings.llm_provider == "9router":
                prov = OpenAICompatibleProvider(
                    settings.ninerouter_base_url,
                    settings.ninerouter_api_key or "sk-dummy",
                    settings.ninerouter_model or "loker-draft",
                )
                models = prov.list_models()
                test_res = prov.complete([{"role": "user", "content": "Tes satu kata."}])
                return {"ok": True, "message": f"9Router terhubung. {len(models)} model tersedia. Model test: {test_res.model}", "model": test_res.model}
            elif settings.llm_provider == "anthropic" and settings.anthropic_api_key:
                from bot_loker_wfh.llm import AnthropicProvider
                prov = AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model)
                test_res = prov.complete([{"role": "user", "content": "Tes satu kata."}])
                return {"ok": True, "message": f"Anthropic terhubung. Model: {test_res.model}", "model": test_res.model}
            elif settings.llm_provider == "opencode":
                return {"ok": False, "error": "OpenCode test not implemented yet"}
            else:
                return {"ok": False, "error": "No LLM provider configured"}
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

    def _get_skills(self):
        """Get skills from OpenCode."""
        try:
            result = subprocess.run(
                ["opencode", "skill", "list", "--json"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                skills = data.get("skills", [])
                return {"skills": skills}
            else:
                return {"skills": [], "error": "opencode skill list failed"}
        except Exception as err:
            return {"skills": [], "error": str(err)}

    def _reload_skills(self):
        """Reload skills from OpenCode."""
        try:
            result = subprocess.run(
                ["opencode", "skill", "reload"],
                capture_output=True, text=True, timeout=30
            )
            return {"ok": result.returncode == 0, "output": result.stdout, "error": result.stderr if result.returncode != 0 else None}
        except Exception as err:
            return {"ok": False, "error": str(err)}

    def _toggle_skill(self, skill_id, enabled):
        """Toggle skill enabled/disabled."""
        try:
            cmd = ["opencode", "skill", "enable" if enabled else "disable", skill_id]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return {"ok": result.returncode == 0, "output": result.stdout, "error": result.stderr if result.returncode != 0 else None}
        except Exception as err:
            return {"ok": False, "error": str(err)}

    def _test_form_engine(self, engine):
        """Test form engine."""
        try:
            from bot_loker_wfh.config import Settings
            settings = Settings.from_environment()
            
            if engine == "browsermcp":
                from bot_loker_wfh.browser_mcp import McpBrowserClient, McpNotConnectedError
                client = McpBrowserClient(command=settings.browser_mcp_command)
                client.start()
                try:
                    client.wait_for_extension(timeout=10.0)
                    client.stop()
                    return {"ok": True, "engine": "browsermcp", "message": "BrowserMCP siap"}
                except McpNotConnectedError:
                    client.stop()
                    return {"ok": False, "engine": "browsermcp", "error": "Ekstensi belum Connect"}
                except Exception as err:
                    client.stop()
                    return {"ok": False, "engine": "browsermcp", "error": str(err)}
            else:
                # Playwright - just check if command works
                cmd = shlex.split(settings.playwright_mcp_command)
                result = subprocess.run(cmd + ["--help"], capture_output=True, text=True, timeout=10)
                return {"ok": result.returncode == 0, "engine": "playwright", "message": "Playwright MCP tersedia" if result.returncode == 0 else "Playwright MCP tidak ditemukan"}
        except Exception as err:
            return {"ok": False, "engine": engine, "error": str(err)}

    def log_message(self, *args):
        pass


def serve(work, port: int = 8765) -> None:
    # Bound to localhost only: the page shows a personal bot's pipeline and cover letters.
    server = ThreadingHTTPServer(("127.0.0.1", port), partial(_Handler, work=work))
    work.start_daily_reports()
    print(f"kantor 3D siap di http://127.0.0.1:{port}  (Ctrl+C untuk berhenti)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
