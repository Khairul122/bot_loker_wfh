import json
import http.client
import shutil
from bot_loker_wfh import database
import tempfile
import threading
import unittest
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.request import Request, urlopen

from bot_loker_wfh import office_server
from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.office_server import _Handler
from bot_loker_wfh.office_work import OfficeWork


class OfficeHttpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db = Path(self.tmp.name) / "app.db"
        connection = database.connect()
        apply_schema(connection)
        connection.close()
        work = OfficeWork(hunters={}, draft_service_for=lambda c: None, form_assist_enabled=False,
                          interval_seconds=3600, lock=threading.Lock())
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Handler, work=work))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}/"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def call(self, path, body=None, headers=None):
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        req = Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                      headers=request_headers)
        try:
            with urlopen(req) as r:
                return r.status, json.loads(r.read())  # one JSON document, never two
        except Exception as error:  # HTTPError carries the status
            return error.code, json.loads(error.read())

    def test_a_failing_request_answers_json_instead_of_closing_the_socket(self):
        with mock.patch.object(office_server, "collect_stats", side_effect=RuntimeError("boom")):
            self.assertEqual(self.call("stats.json"), (500, {"error": "server_error"}))
        with mock.patch.object(office_server, "collect_stats", side_effect=database.OperationalError("down")):
            self.assertEqual(self.call("stats.json"), (503, {"error": "supabase_unavailable"}))

    def test_employee_skills_routes(self):
        status, data = self.call("employee-skills.json")
        self.assertEqual(status, 200)
        self.assertIn("reno", data["employees"])
        status, data = self.call("employee-skills?id=reno")
        self.assertEqual(status, 200)
        self.assertEqual(data["id"], "reno")
        self.assertIn("#", data["markdown"])
        self.assertEqual(self.call("employee-skills?id=../reno")[0], 404)

    def test_llm_readiness_reports_configured_upstream_route(self):
        from types import SimpleNamespace

        settings = SimpleNamespace(
            hermes_base_url="http://127.0.0.1:8642/v1",
            hermes_api_key="secret-not-returned",
            hermes_model_draft="loker-draft",
            hermes_model_form="loker-form",
            hermes_model_answer="loker-answer",
            hermes_api_provider="custom:9router-local",
            hermes_api_model="LokerHouse",
            llm_timeout_seconds=30,
        )
        readiness = {
            "ok": True, "status": "ready", "version": "0.21.7",
            "toolsets": ["skills", "memory", "delegation"], "models": ["loker-answer"],
        }
        with mock.patch("bot_loker_wfh.config.Settings.from_environment", return_value=settings), \
             mock.patch("bot_loker_wfh.llm.HermesAgentClient.check_readiness", return_value=readiness):
            status, data = self.call("llm/test")

        self.assertEqual(status, 200)
        self.assertEqual((data["provider"], data["upstream_model"]), ("custom:9router-local", "LokerHouse"))
        self.assertNotIn("secret-not-returned", json.dumps(data))

    def test_post_rejects_dns_rebinding_origin_and_host(self):
        status, data = self.call(
            "settings",
            {"key": "unknown", "value": "1"},
            headers={"Origin": "http://attacker.invalid", "Host": "attacker.invalid"},
        )
        self.assertEqual((status, data), (403, {"error": "forbidden"}))

    def test_post_allows_same_loopback_origin(self):
        port = self.server.server_address[1]
        status, data = self.call(
            "settings",
            {"key": "unknown", "value": "1"},
            headers={"Origin": f"http://localhost:{port}"},
        )
        self.assertEqual((status, data["error"]), (400, "unknown_setting"))

    def test_websocket_rejects_cross_site_origin_before_upgrade(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=2)
        connection.request(
            "GET",
            "/ws",
            headers={
                "Connection": "Upgrade",
                "Upgrade": "websocket",
                "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
                "Sec-WebSocket-Version": "13",
                "Origin": "http://attacker.invalid",
            },
        )
        response = connection.getresponse()
        self.assertEqual(response.status, 403)
        connection.close()

    def test_desk_routes_answer_exactly_once(self):
        status, data = self.call("reports/request/reno", {})
        self.assertEqual(status, 200)
        report_id = data["items"][0]["id"]
        self.assertEqual(self.call(f"reports/{report_id}/delivered", {})[0], 200)
        self.assertEqual(self.call(f"reports/{report_id}/review", {"rating": 5, "note": "ok"})[1]["rating"], 5)
        self.assertEqual(self.call(f"reports/{report_id}/review", {"rating": 9})[0], 400)
        self.assertEqual(self.call("instructions/cora", {"text": "python"})[1], {"text": "python"})
        self.assertFalse(self.call("ask/reno", {"question": "dapat apa?"})[1]["ai"])
        self.assertEqual(self.call("reports/request/nobody", {})[0], 404)
        self.assertEqual(self.call("work/telegram", {})[1], {"sent": False})
        stats = self.call("stats.json")[1]
        self.assertEqual(stats["desk"]["instructions"], {"cora": "python"})
        self.assertEqual(self.call("employee.json?id=reno")[1]["rating"]["avg"], 5)
        self.assertIn("counts", self.call("leads.json?view=new")[1])

    def test_manager_task_routes_return_client_errors_for_invalid_requests(self):
        self.assertEqual(self.call("manager/brief", {"manager": "rima"}), (404, {"error": "not_manager"}))
        self.assertEqual(self.call("manager/brief", {"manager": "tegar"}), (503, {"error": "hermes_unavailable"}))

        status, data = self.call("manager/tasks", {
            "manager": "rima", "assignee": "rima", "title": "Check candidate summary",
        })
        self.assertEqual((status, data), (404, {"error": "not_manager"}))

        status, data = self.call("manager/tasks", {
            "manager": "tegar", "assignee": "reno", "title": "Check candidate summary",
        })
        self.assertEqual((status, data), (400, {"error": "assignee_must_be_in_managed_division"}))

        status, data = self.call("manager/tasks", {
            "manager": "tegar", "assignee": "tegar", "title": "No",
        })
        self.assertEqual((status, data), (400, {"error": "invalid_title"}))

    def test_manager_brief_route_records_validated_hermes_assignments(self):
        from bot_loker_wfh import manager_tasks
        with mock.patch.object(manager_tasks, "division_brief", return_value={
            "division": {"id": "lobi", "name": "Lobi & Operasional", "manager": "tegar"},
            "summary": "Antrean owner perlu dirapikan.",
            "priorities": [{"title": "Periksa antrean persetujuan", "assignee": "tegar", "priority": "high"}],
        }), mock.patch.object(manager_tasks, "assign_recommendations", return_value=[{
            "id": "task-1", "division": "lobi", "manager": "tegar", "assignee": "tegar",
            "assignee_name": "Tegar", "title": "Periksa antrean persetujuan", "priority": "high",
            "status": "assigned", "review_note": "",
        }]):
            status, data = self.call("manager/brief", {"manager": "tegar"})
        self.assertEqual(status, 200)
        self.assertEqual(data["assigned_tasks"][0]["assignee_name"], "Tegar")

        status, data = self.call("manager/tasks/unknown", {
            "manager": "tegar", "status": "sent_to_client",
        })
        self.assertEqual((status, data), (400, {"error": "invalid_status"}))


class SettingsHttpTest(unittest.TestCase):
    """Settings routes backed by the app_settings table."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db = Path(self.tmp.name) / "app.db"
        with database.connect() as connection:
            apply_schema(connection)
        work = OfficeWork(hunters={}, draft_service_for=lambda c: None, form_assist_enabled=False,
                          interval_seconds=3600, lock=threading.Lock())
        self.db = db
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Handler, work=work))
        self.server.daemon_threads = True
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}/"
        # never let a settings POST touch the real .env on disk
        self._dotenv = mock.patch.object(office_server, "save_dotenv", lambda *a, **k: None)
        self._dotenv.start()

    def tearDown(self):
        self._dotenv.stop()
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=2)
        try:
            self.tmp.cleanup()
        except PermissionError:
            shutil.rmtree(self.tmp.name, ignore_errors=True)

    def call(self, path, body=None):
        req = Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                      headers={"Content-Type": "application/json"})
        try:
            with urlopen(req) as r:
                return r.status, json.loads(r.read())
        except Exception as error:
            return error.code, json.loads(error.read())

    def test_offline_settings_still_serve_and_never_leak_secret(self):
        status, data = self.call("settings.json")
        self.assertEqual(status, 200)
        self.assertEqual(data["hermes_api_key"]["value"], "")
        self.assertNotIn("sk-", json.dumps(data))

    def test_stored_settings_are_served_and_secret_is_masked(self):
        self.call("settings", {"key": "llm_provider", "value": "hermes"})
        self.call("settings", {"key": "hermes_api_key", "value": "hermes-live-123456"})
        status, data = self.call("settings.json")
        self.assertEqual(status, 200)
        self.assertEqual(data["llm_provider"]["value"], "hermes")
        self.assertTrue(data["hermes_api_key"]["set"])
        self.assertNotIn("hermes-live-123456", json.dumps(data))

    def test_post_is_stored_in_database(self):
        status, data = self.call("settings", {"key": "scrape_interval_hours", "value": "9"})
        self.assertEqual(status, 200)
        with database.connect() as connection:
            row = connection.execute("SELECT value FROM app_settings WHERE key = 'scrape_interval_hours'").fetchone()
        self.assertEqual(row[0], "9")

    def test_database_failure_is_503_not_false_success(self):
        with mock.patch.object(office_server, "set_setting", mock.Mock(side_effect=database.OperationalError("down"))):
            status, data = self.call("settings", {"key": "scrape_interval_hours", "value": "9"})
        self.assertEqual(status, 503)
        self.assertEqual(data, {"error": "supabase_unavailable"})

    def test_blank_secret_keeps_stored_value(self):
        self.call("settings", {"key": "hermes_api_key", "value": "hermes-keep-1234"})
        status, data = self.call("settings", {"key": "hermes_api_key", "value": ""})
        self.assertEqual(status, 200)
        self.assertTrue(data["hermes_api_key"]["set"])

    def test_unknown_setting_is_rejected(self):
        status, data = self.call("settings", {"key": "drop_table", "value": "1"})
        self.assertEqual(status, 400)

    def test_batch_post_stores_every_value_in_one_request(self):
        status, data = self.call("settings", {"values": {"hermes_model_draft": "A", "form_ai_answers": "off", "form_max_actions": "42"}})
        self.assertEqual(status, 200)
        with database.connect() as connection:
            stored = dict(connection.execute("SELECT key, value FROM app_settings").fetchall())
        self.assertEqual((stored["hermes_model_draft"], stored["form_ai_answers"], stored["form_max_actions"]), ("A", "off", "42"))
        self.assertEqual(data["form_ai_answers"]["value"], "off")

    def test_batch_with_one_bad_value_stores_nothing(self):
        status, data = self.call("settings", {"values": {"hermes_model_draft": "B", "form_max_actions": "abc"}})
        self.assertEqual((status, data["key"]), (400, "form_max_actions"))
        with database.connect() as connection:
            row = connection.execute("SELECT 1 FROM app_settings WHERE key = 'hermes_model_draft'").fetchone()
        self.assertIsNone(row)

    def test_owner_prefs_roundtrip(self):
        look = json.dumps({"name": "Bos", "skin": "#f1c9a5", "hair": "#3b2a20", "shirt": "#ffb26b", "pants": "#4a5a7a"})
        self.assertEqual(self.call("office/prefs", {"key": "look", "value": look})[0], 200)
        self.assertEqual(self.call("office/prefs", {"key": "sound", "value": "1"})[0], 200)
        self.assertEqual(self.call("office/prefs", {"key": "auto", "value": "0"})[0], 200)
        status, data = self.call("office/prefs.json")
        self.assertEqual((status, data["sound"], data["auto"]), (200, "1", "0"))
        self.assertEqual(json.loads(data["look"])["name"], "Bos")

    def test_owner_prefs_reject_bad_input(self):
        self.assertEqual(self.call("office/prefs", {"key": "look", "value": '{"name": "x", "skin": "red"}'})[0], 400)
        self.assertEqual(self.call("office/prefs", {"key": "sound", "value": "yes"})[0], 400)
        self.assertEqual(self.call("office/prefs", {"key": "drop", "value": "1"})[0], 400)

    def test_profile_is_saved_and_validated(self):
        for key, value in (("freelancer", "https://www.freelancer.com/u/me"), ("linkedin", "https://www.linkedin.com/in/me"), ("github", "octocat")):
            self.assertEqual(self.call("office/prefs", {"key": key, "value": value})[0], 200)
        data = self.call("office/prefs.json")[1]
        self.assertEqual((data["github"], data["linkedin"]), ("octocat", "https://www.linkedin.com/in/me"))
        self.assertEqual(self.call("office/prefs", {"key": "linkedin", "value": "javascript:alert(1)"})[0], 400)
        self.assertEqual(self.call("office/prefs", {"key": "github", "value": "bad name!"})[0], 400)

    def test_github_sync_stores_portfolio_in_database(self):
        repo = {"name": "demo", "description": "d", "language": "Python", "topics": [], "stargazers_count": 1, "fork": False, "archived": False,
                "html_url": "https://github.com/octocat/demo", "pushed_at": "2026-01-01T00:00:00Z"}
        with mock.patch("bot_loker_wfh.github_portfolio.fetch_repos", return_value=[repo]):
            status, data = self.call("github/sync", {"username": "octocat"})
        self.assertEqual((status, data["repos"]), (200, 1))
        stored = self.call("github.json")[1]
        self.assertEqual((stored["username"], stored["repos"]), ("octocat", 1))

    def test_github_sync_uses_saved_username_when_none_given(self):
        self.call("office/prefs", {"key": "github", "value": "octocat"})
        with mock.patch("bot_loker_wfh.github_portfolio.fetch_repos", return_value=[]) as fetch:
            status, data = self.call("github/sync", {})
        self.assertEqual((status, data["username"]), (200, "octocat"))
        fetch.assert_called_once()

    def test_github_unknown_user_is_404_not_unreachable(self):
        from urllib.error import HTTPError
        error = HTTPError("https://api.github.com/users/nobody/repos", 404, "Not Found", {}, None)
        with mock.patch("bot_loker_wfh.github_portfolio.fetch_repos", side_effect=error):
            status, data = self.call("github/sync", {"username": "nobody"})
        self.assertEqual((status, data["error"]), (404, "github_user_not_found"))

    def test_auto_bid_settings_default_off_roundtrip_and_validation(self):
        self.assertEqual(self.call("settings.json")[1]["auto_bid_enabled"]["value"], "0")
        status, data = self.call("settings", {"values": {"auto_bid_enabled": "1", "auto_bid_max_per_day": "3"}})
        self.assertEqual((status, data["auto_bid_enabled"]["value"], data["auto_bid_max_per_day"]["value"]), (200, "1", "3"))
        self.assertEqual(self.call("settings", {"key": "auto_bid_enabled", "value": "2"})[0], 400)
        self.assertEqual(self.call("settings", {"key": "auto_bid_max_per_day", "value": "500"})[0], 400)


if __name__ == "__main__":
    unittest.main()
