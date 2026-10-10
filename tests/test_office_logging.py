"""Every employee action reaches the owner's terminal as one structured JSON line."""

import io
import json
import logging
import sqlite3
import tempfile
import threading
import unittest
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from bot_loker_wfh import office_desk as desk
from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.drafts import DraftResult
from bot_loker_wfh.office_server import _Handler
from bot_loker_wfh.office_work import OfficeWork


def insert_job(connection, job_id, status="CANDIDATE", score=0.9):
    connection.execute(
        "INSERT INTO jobs (id, source, external_id, source_external_key, canonical_fingerprint, "
        "title, company, description, location, apply_url, status, relevance_score) "
        "VALUES (?, 'remoteok', ?, ?, ?, 'Laravel Dev', 'Acme', 'd', 'Remote', "
        "'https://example.com/apply', ?, ?)",
        (job_id, job_id, f"remoteok:{job_id}", f"fp-{job_id}", status, score),
    )


def insert_application(connection, app_id, job_id, status="PENDING_APPROVAL"):
    connection.execute(
        "INSERT INTO applications (id, job_id, idempotency_key, status, cover_letter, cv_summary) "
        "VALUES (?, ?, ?, ?, 'Dear Acme', 'CV')",
        (app_id, job_id, f"key-{app_id}", status),
    )


def insert_lead(connection, lead_id, source="freelancer", status="NEW"):
    connection.execute(
        "INSERT INTO leads (id, source, external_id, kind, title, description, url, budget, status) "
        "VALUES (?, ?, ?, 'project', 'Build API', 'Need a Laravel API', 'https://example.com/p', '$200', ?)",
        (lead_id, source, lead_id, status),
    )


class FakeDrafts:
    def __init__(self, connection):
        self.connection = connection

    def prepare(self, job_id):
        insert_application(self.connection, f"app-{job_id}", job_id)
        return DraftResult("created", f"app-{job_id}", "PENDING_APPROVAL")


class EmployeeActivityLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "app.db"
        self.connection = sqlite3.connect(self.db)
        apply_schema(self.connection)
        self.stream = io.StringIO()
        self.logger = logging.getLogger("office-activity-test")
        self.logger.handlers.clear()
        self.logger.propagate = False
        handler = logging.StreamHandler(self.stream)
        handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    def tearDown(self):
        self.connection.close()
        self.tmp.cleanup()

    def records(self):
        return [json.loads(line) for line in self.stream.getvalue().splitlines() if line.strip()]

    def make_work(self, **kwargs):
        options = dict(
            hunters={}, draft_service_for=FakeDrafts, form_assist_enabled=False,
            interval_seconds=4 * 3600, lock=threading.Lock(), logger=self.logger,
        )
        options.update(kwargs)
        return OfficeWork(self.db, **options)

    def test_cycle_logs_one_line_per_scout_with_its_employee_name(self):
        def ok(connection):
            return {"inserted": 2, "matched": 1, "top": []}

        def broken(connection):
            raise ConnectionError("secret-url-should-not-appear")

        work = self.make_work(hunters={"remoteok": ok, "broken": broken})
        work.auto = True
        work.run_cycle()

        hunts = {record["source"]: record for record in self.records() if record["task"] == "hunt"}
        self.assertEqual(
            (hunts["remoteok"]["employee"], hunts["remoteok"]["status"], hunts["remoteok"]["matched"]),
            ("reno", "success", 1),
        )
        self.assertEqual(hunts["remoteok"]["inserted_count"], 2)
        self.assertEqual(
            (hunts["broken"]["employee"], hunts["broken"]["status"], hunts["broken"]["error_code"]),
            ("-", "error", "network_error"),
        )
        # a broken source must not stop the rest of the cycle
        self.assertEqual(work.last["source"], "draft")
        self.assertIsNone(work.busy)

    def test_cycle_logs_cora_drafting_and_keeps_letters_out_of_the_log(self):
        insert_job(self.connection, "j1")
        self.connection.commit()
        work = self.make_work()
        work.auto = True
        work.run_cycle()

        drafts = [record for record in self.records() if record["task"] == "draft"]
        self.assertEqual((drafts[0]["employee"], drafts[0]["count"]), ("cora", 1))
        self.assertNotIn("Dear Acme", self.stream.getvalue())

    def test_owner_decision_is_logged_by_tegar_with_the_application_id(self):
        insert_job(self.connection, "j")
        insert_application(self.connection, "a", "j")
        work = self.make_work()

        result = work.decide(self.connection, "a", "approve")

        decision = [record for record in self.records() if record["task"] == "decision"][0]
        self.assertEqual(
            (decision["employee"], decision["action"], decision["application_id"], decision["status"]),
            ("tegar", "approve", "a", result["status"]),
        )
        self.assertNotIn("Dear Acme", self.stream.getvalue())

    def test_stale_decision_logs_an_error_line_and_still_raises(self):
        from bot_loker_wfh.status_transitions import InvalidTransitionError

        insert_job(self.connection, "j")
        insert_application(self.connection, "a", "j")
        work = self.make_work()

        with self.assertRaises(InvalidTransitionError):
            work.decide(self.connection, "a", "apply")

        failure = [record for record in self.records() if record["status"] == "error"][0]
        self.assertEqual((failure["employee"], failure["task"], failure["action"]), ("tegar", "decision", "apply"))

    def test_lead_actions_name_the_employee_who_did_them(self):
        insert_lead(self.connection, "l1")
        insert_lead(self.connection, "l2")
        work = self.make_work()

        work.lead_action(self.connection, "l1", "interested", {})
        work.lead_action(self.connection, "l2", "proposal", {"text": "My bid"})

        leads = [record for record in self.records() if record["task"] == "lead"]
        self.assertEqual(
            [(record["employee"], record["action"], record["lead_id"]) for record in leads],
            [("bimo", "interested", "l1"), ("cora", "proposal", "l2")],
        )
        self.assertNotIn("My bid", self.stream.getvalue())

    def test_reports_and_instructions_are_logged_per_employee(self):
        work = self.make_work()

        work.request_reports(self.connection, "reno")
        work.daily_reports(self.connection)

        reports = [record for record in self.records() if record["task"] == "report"]
        self.assertEqual(reports[0]["employee"], "reno")  # the button asked one employee
        self.assertEqual(len(reports), 1 + len(desk.EMPLOYEES))  # the morning round asks everyone
        self.assertEqual({r["employee"] for r in reports[1:]}, set(desk.EMPLOYEES))
        self.assertEqual(reports[1]["mode"], "daily")

    def test_telegram_failure_is_logged_and_the_report_survives(self):
        def boom(text):
            raise ConnectionError("telegram down")

        insert_job(self.connection, "j")
        self.connection.commit()
        work = self.make_work(notify=boom)

        result = work.request_reports(self.connection, "reno")  # must not raise

        self.assertEqual(len(result["items"]), 1)
        failure = [record for record in self.records() if record["task"] == "telegram"][0]
        self.assertEqual((failure["employee"], failure["error_code"]), ("tegar", "network_error"))

    def test_digest_reports_how_many_employees_were_summarized(self):
        insert_job(self.connection, "j")
        self.connection.commit()
        sent = []
        work = self.make_work(notify=sent.append)

        self.assertEqual(work.telegram_digest(self.connection), {"sent": True})

        digest = [record for record in self.records() if record["task"] == "digest"][0]
        self.assertEqual((digest["employee"], digest["count"]), ("tegar", len(desk.EMPLOYEES)))
        self.assertEqual(len(sent), 1)


class ManualOfficeActionLogTest(unittest.TestCase):
    """The 3D page's buttons leave the same kind of line in the terminal."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "app.db"
        connection = sqlite3.connect(self.db)
        apply_schema(connection)
        connection.close()
        self.stream = io.StringIO()
        logger = logging.getLogger("office-manual-test")
        logger.handlers.clear()
        logger.propagate = False
        handler = logging.StreamHandler(self.stream)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        self.work = OfficeWork(
            self.db, hunters={"remoteok": lambda connection: {"inserted": 1, "matched": 3, "top": []}},
            draft_service_for=FakeDrafts, form_assist_enabled=False, interval_seconds=3600,
            lock=threading.Lock(), logger=logger,
            screener=lambda connection: {"matched": 2, "filtered_out": 5},
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Handler, work=self.work))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}/"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def records(self):
        return [json.loads(line) for line in self.stream.getvalue().splitlines() if line.strip()]

    def post(self, path, body=None):
        request = Request(
            self.base + path, data=json.dumps(body or {}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            return response.status, json.loads(response.read())

    def test_hunt_button_logs_the_scout_and_the_screen_button_logs_sari(self):
        self.assertEqual(self.post("hunt/remoteok")[0], 200)
        self.assertEqual(self.post("work/screen")[0], 200)

        hunt = [record for record in self.records() if record["task"] == "hunt"][0]
        self.assertEqual((hunt["employee"], hunt["source"], hunt["matched"], hunt["inserted_count"]),
                         ("reno", "remoteok", 3, 1))
        self.assertIsInstance(hunt["duration_ms"], int)
        screen = [record for record in self.records() if record["task"] == "screen"]
        # Sari scores what survived, Eli reports what got thrown out
        self.assertEqual([(record["employee"], record["matched"]) for record in screen if "matched" in record],
                         [("sari", 2)])
        self.assertEqual([(record["employee"], record["count"]) for record in screen if "count" in record],
                         [("eli", 5)])

    def test_polling_the_dashboard_is_never_logged(self):
        with urlopen(self.base + "stats.json") as response:
            self.assertEqual(response.status, 200)

        self.assertEqual(self.records(), [])


if __name__ == "__main__":
    unittest.main()
