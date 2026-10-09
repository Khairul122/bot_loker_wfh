import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.drafts import DraftResult
from bot_loker_wfh.office_work import OfficeWork
from bot_loker_wfh.status_transitions import InvalidTransitionError


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


class FakeDrafts:
    def __init__(self, connection):
        self.connection = connection

    def prepare(self, job_id):
        insert_application(self.connection, f"app-{job_id}", job_id)
        return DraftResult("created", f"app-{job_id}", "PENDING_APPROVAL")


class OfficeWorkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "app.db"
        self.connection = sqlite3.connect(self.db)
        apply_schema(self.connection)
        self.spawned = []
        self.work = self.make_work(form_assist_enabled=False)

    def tearDown(self):
        self.connection.close()
        self.tmp.cleanup()

    def make_work(self, *, form_assist_enabled, hunters=None):
        return OfficeWork(
            self.db,
            hunters=hunters or {},
            draft_service_for=FakeDrafts,
            form_assist_enabled=form_assist_enabled,
            interval_seconds=4 * 3600,
            lock=threading.Lock(),
            spawn=lambda cmd, **kwargs: self.spawned.append(cmd),
        )

    def status(self, app_id):
        return self.connection.execute(
            "SELECT status FROM applications WHERE id = ?", (app_id,)
        ).fetchone()[0]

    def test_draft_next_drafts_best_undrafted_candidates_and_inbox_lists_them(self):
        insert_job(self.connection, "low", score=0.5)
        insert_job(self.connection, "high", score=0.95)
        insert_job(self.connection, "filtered", status="FILTERED_OUT")

        self.assertEqual(self.work.draft_next(self.connection, limit=1), 1)
        inbox = self.work.inbox(self.connection)

        self.assertEqual([item["id"] for item in inbox["pending"]], ["app-high"])
        self.assertEqual(inbox["pending"][0]["letter"], "Dear Acme")
        self.assertEqual(inbox["waiting"], 1)

    def test_approve_without_form_assist_hands_the_link_to_the_owner(self):
        insert_job(self.connection, "j")
        insert_application(self.connection, "a", "j")

        result = self.work.decide(self.connection, "a", "approve")

        self.assertEqual(result, {"status": "APPROVED", "mode": "manual", "url": "https://example.com/apply"})
        self.assertEqual(self.status("a"), "APPROVED")
        self.assertEqual(self.spawned, [])

    def test_nothing_is_applied_before_approval(self):
        insert_job(self.connection, "j")
        insert_application(self.connection, "a", "j")
        work = self.make_work(form_assist_enabled=True)

        with self.assertRaises(InvalidTransitionError):
            work.decide(self.connection, "a", "apply")
        with self.assertRaises(InvalidTransitionError):
            work.decide(self.connection, "a", "applied")
        self.assertEqual(self.spawned, [])
        self.assertEqual(self.status("a"), "PENDING_APPROVAL")

    def test_reject_then_stale_approve_is_refused(self):
        insert_job(self.connection, "j")
        insert_application(self.connection, "a", "j")

        self.assertEqual(self.work.decide(self.connection, "a", "reject"), {"status": "REJECTED_BY_USER"})
        with self.assertRaises(InvalidTransitionError):
            self.work.decide(self.connection, "a", "approve")

    def test_applied_marks_submitted_after_approval(self):
        insert_job(self.connection, "j")
        insert_application(self.connection, "a", "j", status="APPROVED")

        self.assertEqual(self.work.decide(self.connection, "a", "applied"), {"status": "SUBMITTED"})
        self.assertEqual(self.status("a"), "SUBMITTED")

    def test_cycle_runs_every_hunter_then_drafts_and_survives_a_broken_source(self):
        insert_job(self.connection, "j")
        self.connection.commit()
        calls = []

        def ok(connection):
            calls.append("ok")
            return {"inserted": 3, "matched": 1, "top": []}

        def broken(connection):
            calls.append("broken")
            raise OSError("network down")

        work = self.make_work(form_assist_enabled=False, hunters={"broken": broken, "ok": ok})
        work.auto = True
        work.run_cycle()

        self.assertEqual(calls, ["broken", "ok"])
        self.assertEqual(work.last["source"], "draft")
        self.assertEqual(work.last["matched"], 1)
        self.assertIsNone(work.busy)
        self.assertEqual(self.status("app-j"), "PENDING_APPROVAL")


if __name__ == "__main__":
    unittest.main()
