import json
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

from bot_loker_wfh import office_server, settings_store
from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.office_server import _Handler
from bot_loker_wfh.office_work import OfficeWork
from bot_loker_wfh.settings_store import SupabaseUnavailable


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

    def call(self, path, body=None):
        req = Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                      headers={"Content-Type": "application/json"})
        try:
            with urlopen(req) as r:
                return r.status, json.loads(r.read())  # one JSON document, never two
        except Exception as error:  # HTTPError carries the status
            return error.code, json.loads(error.read())

    def test_employee_skills_routes(self):
        status, data = self.call("employee-skills.json")
        self.assertEqual(status, 200)
        self.assertIn("reno", data["employees"])
        status, data = self.call("employee-skills?id=reno")
        self.assertEqual(status, 200)
        self.assertEqual(data["id"], "reno")
        self.assertIn("#", data["markdown"])
        self.assertEqual(self.call("employee-skills?id=../reno")[0], 404)

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


class SettingsCloudHttpTest(unittest.TestCase):
    """Settings routes against a mocked Supabase backend (no network)."""

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
        self.assertEqual(data["ninerouter_api_key"]["value"], "")
        self.assertNotIn("sk-", json.dumps(data))

    def test_cloud_get_is_authoritative_and_masks_secret(self):
        with mock.patch.object(settings_store, "cloud_configured", lambda: True), \
             mock.patch.object(settings_store, "fetch_cloud_settings",
                               lambda: {"llm_provider": "9router", "ninerouter_api_key": "sk-live-123456"}):
            status, data = self.call("settings.json")
        self.assertEqual(status, 200)
        self.assertEqual(data["llm_provider"]["value"], "9router")
        self.assertTrue(data["ninerouter_api_key"]["set"])
        self.assertNotIn("sk-live-123456", json.dumps(data))

    def test_cloud_get_failure_is_503_not_stale_success(self):
        with mock.patch.object(settings_store, "cloud_configured", lambda: True), \
             mock.patch.object(settings_store, "fetch_cloud_settings",
                               mock.Mock(side_effect=SupabaseUnavailable("down"))):
            status, data = self.call("settings.json")
        self.assertEqual(status, 503)
        self.assertEqual(data, {"error": "supabase_unavailable"})

    def test_cloud_post_writes_then_applies_runtime(self):
        store = mock.Mock()
        with mock.patch.object(settings_store, "cloud_configured", lambda: True), \
             mock.patch.object(settings_store, "store_cloud_setting", store):
            status, data = self.call("settings", {"key": "llm_provider", "value": "9router"})
        self.assertEqual(status, 200)
        store.assert_called_once_with("llm_provider", "9router")
        self.assertEqual(data["llm_provider"]["value"], "9router")

    def test_cloud_post_failure_is_503_and_not_applied(self):
        store = mock.Mock(side_effect=SupabaseUnavailable("down"))
        with mock.patch.object(settings_store, "cloud_configured", lambda: True), \
             mock.patch.object(settings_store, "store_cloud_setting", store):
            status, data = self.call("settings", {"key": "scrape_interval_hours", "value": "9"})
        self.assertEqual(status, 503)
        self.assertEqual(data, {"error": "supabase_unavailable"})
        store.assert_called_once_with("scrape_interval_hours", "9")
        # cloud failed -> local cache must not have been written
        with database.connect() as connection:
            row = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'scrape_interval_hours'"
            ).fetchone()
        self.assertEqual(row[0], "4")

    def test_blank_secret_keeps_cloud_value(self):
        with mock.patch.object(settings_store, "cloud_configured", lambda: True), \
             mock.patch.object(settings_store, "fetch_cloud_settings",
                               lambda: {"ninerouter_api_key": "sk-keep-1234"}):
            status, data = self.call("settings", {"key": "ninerouter_api_key", "value": ""})
        self.assertEqual(status, 200)
        self.assertTrue(data["ninerouter_api_key"]["set"])

    def test_unknown_setting_rejected_before_cloud(self):
        store = mock.Mock()
        with mock.patch.object(settings_store, "cloud_configured", lambda: True), \
             mock.patch.object(settings_store, "store_cloud_setting", store):
            status, data = self.call("settings", {"key": "drop_table", "value": "1"})
        self.assertEqual(status, 400)
        store.assert_not_called()


if __name__ == "__main__":
    unittest.main()
