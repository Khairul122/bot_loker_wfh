import json
import sqlite3
import tempfile
import threading
import unittest
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.office_server import _Handler
from bot_loker_wfh.office_work import OfficeWork


class OfficeHttpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db = Path(self.tmp.name) / "app.db"
        connection = sqlite3.connect(db)
        apply_schema(connection)
        connection.close()
        work = OfficeWork(db, hunters={}, draft_service_for=lambda c: None, form_assist_enabled=False,
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


if __name__ == "__main__":
    unittest.main()
