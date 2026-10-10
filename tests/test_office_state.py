import json
import sqlite3
import tempfile
import threading
import shutil
import unittest
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.request import Request, urlopen

from bot_loker_wfh import office_server, settings_store
from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.office_server import _Handler
from bot_loker_wfh.office_state import load_state, save_state
from bot_loker_wfh.office_work import OfficeWork
from bot_loker_wfh.settings_store import SupabaseUnavailable


class OfficeStateTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)

    def tearDown(self):
        self.connection.close()

    def test_state_round_trip_and_update(self):
        state = {"owner": {"x": 1, "y": 2, "z": 3, "yaw": 0.5},
                 "staff": {"cora": {"x": 4, "y": 5, "z": 6}}}
        self.assertEqual(save_state(self.connection, state), {
            "owner": {"x": 1.0, "y": 2.0, "z": 3.0, "yaw": 0.5},
            "staff": {"cora": {"x": 4.0, "y": 5.0, "z": 6.0, "yaw": 0.0}},
        })
        save_state(self.connection, {"staff": {"cora": {"x": 7, "y": 8, "z": 9}}})
        self.assertEqual(load_state(self.connection)["staff"]["cora"]["x"], 7.0)

    def test_rejects_non_finite_coordinates(self):
        with self.assertRaises(ValueError):
            save_state(self.connection, {"owner": {"x": "nan", "y": 0, "z": 0}})


class OfficeStateHttpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db = Path(self.tmp.name) / "app.db"
        with sqlite3.connect(db) as connection:
            apply_schema(connection)
        work = OfficeWork(db, hunters={}, draft_service_for=lambda c: None, form_assist_enabled=False,
                          interval_seconds=3600, lock=threading.Lock())
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Handler, work=work))
        self.server.daemon_threads = True
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}/"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=2)
        try:
            self.tmp.cleanup()
        except PermissionError:
            shutil.rmtree(self.tmp.name, ignore_errors=True)

    def call(self, path, body=None):
        request = Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                          headers={"Content-Type": "application/json"})
        try:
            with urlopen(request) as response:
                return response.status, json.loads(response.read())
        except Exception as error:
            return error.code, json.loads(error.read())

    def test_state_routes(self):
        self.assertEqual(self.call("office/state.json")[1], {"owner": None, "staff": {}})
        self.assertEqual(self.call("office/character-state", {
            "owner": {"x": 1, "y": 0, "z": 2}, "staff": {}
        })[0], 200)
        self.assertEqual(self.call("office/state.json")[1]["owner"]["x"], 1.0)
        self.assertEqual(self.call("office/character-state", {"owner": {"x": "bad"}})[0], 400)

    def test_cloud_backend_down_is_503(self):
        with mock.patch.object(settings_store, "cloud_configured", lambda: True), \
             mock.patch.object(office_server, "load_state",
                               mock.Mock(side_effect=SupabaseUnavailable("down"))):
            status, data = self.call("office/state.json")
        self.assertEqual(status, 503)
        self.assertEqual(data, {"error": "supabase_unavailable"})


if __name__ == "__main__":
    unittest.main()
