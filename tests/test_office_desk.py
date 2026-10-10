from bot_loker_wfh import database
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path

from bot_loker_wfh import office_desk as desk
from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.office_work import OfficeWork


def insert_job(connection, job_id, *, source="remoteok", status="CANDIDATE", title="Laravel Dev", score=0.5):
    connection.execute(
        "INSERT INTO jobs (id, source, external_id, source_external_key, canonical_fingerprint, "
        "title, company, description, apply_url, status, relevance_score) "
        "VALUES (?, ?, ?, ?, ?, ?, 'Acme', 'd', 'https://x', ?, ?)",
        (job_id, source, job_id, f"{source}:{job_id}", f"fp-{job_id}", title, status, score),
    )


class DeskTest(unittest.TestCase):
    def setUp(self):
        self.connection = database.connect()
        apply_schema(self.connection)

    def test_scout_report_counts_only_its_source_in_the_window(self):
        insert_job(self.connection, "a")
        insert_job(self.connection, "b", status="FILTERED_OUT")
        insert_job(self.connection, "c", source="lever")
        insert_job(self.connection, "old")
        self.connection.execute("UPDATE jobs SET fetched_at = '2000-01-01T00:00:00.000Z' WHERE id = 'old'")

        report = desk.create_report(self.connection, "reno")

        self.assertEqual(report["metrics"], [["🔎", "Lowongan baru", 2], ["✅", "Cocok", 1]])
        self.assertIsNone(report["delivered_at"])
        self.assertEqual(desk.undelivered(self.connection), [{"id": report["id"], "employee": "reno", "lines": report["lines"]}])

    def test_every_employee_can_report(self):
        for employee in desk.EMPLOYEES:
            report = desk.create_report(self.connection, employee)
            self.assertTrue(0 <= report["score"] <= 1, employee)
            self.assertTrue(report["lines"], employee)

    def test_daily_round_runs_once_per_day_and_only_after_the_morning_hour(self):
        self.assertEqual(desk.ensure_daily_reports(self.connection, datetime(2026, 10, 9, 6)), [])
        first = desk.ensure_daily_reports(self.connection, datetime(2026, 10, 9, 9))
        self.assertEqual(len(first), len(desk.EMPLOYEES))
        self.assertEqual(desk.ensure_daily_reports(self.connection, datetime(2026, 10, 9, 15)), [])
        self.assertEqual(len(desk.ensure_daily_reports(self.connection, datetime(2026, 10, 10, 9))), len(desk.EMPLOYEES))

    def test_review_is_validated_and_feeds_the_rating_average(self):
        r1 = desk.create_report(self.connection, "cora")
        r2 = desk.create_report(self.connection, "cora")
        desk.review_report(self.connection, r1["id"], 5, "mantap")
        desk.review_report(self.connection, r2["id"], 2, "")
        with self.assertRaises(ValueError):
            desk.review_report(self.connection, r1["id"], 9)
        with self.assertRaises(KeyError):
            desk.review_report(self.connection, "missing", 3)
        self.assertEqual(desk.ratings(self.connection)["cora"]["avg"], 3.5)
        desk.mark_delivered(self.connection, r1["id"])
        self.assertEqual([u["id"] for u in desk.undelivered(self.connection)], [r2["id"]])
        self.assertEqual(desk.tray_count(self.connection), 0)  # r1 is delivered but already rated

    def test_instruction_is_appended_to_prompts_and_ranks_results(self):
        desk.set_instruction(self.connection, "cora", "Tekankan pengalaman Django")
        seen = []
        llm = desk.instructed(lambda prompt: seen.append(prompt) or "ok", self.connection, "cora")
        llm("Write a letter")
        self.assertIn("Tekankan pengalaman Django", seen[0])
        self.assertEqual(desk.set_instruction(self.connection, "cora", "  "), "")
        self.assertEqual(desk.instructions(self.connection), {})
        with self.assertRaises(KeyError):
            desk.set_instruction(self.connection, "nobody", "x")

        items = [{"title": "PHP dev"}, {"title": "Python Django dev"}, {"title": "Go dev"}]
        ranked = desk.prioritize(items, desk.keywords("fokus python, django"))
        self.assertEqual(ranked[0]["title"], "Python Django dev")
        self.assertEqual(desk.prioritize(items, []), items)

    def test_profile_has_three_periods_and_trend(self):
        insert_job(self.connection, "a")
        r = desk.create_report(self.connection, "reno")
        desk.review_report(self.connection, r["id"], 4, "bagus")
        p = desk.profile(self.connection, "reno")
        self.assertEqual(list(p["periods"]), ["24 jam", "7 hari", "30 hari"])
        self.assertEqual(p["periods"]["30 hari"]["metrics"][0][2], 1)
        self.assertEqual([h["rating"] for h in p["history"]], [4])
        self.assertEqual(p["notes"][0]["note"], "bagus")
        with self.assertRaises(KeyError):
            desk.profile(self.connection, "nobody")

    def test_lead_board_filters(self):
        from bot_loker_wfh.lead_desk import lead_counts, list_leads
        rows = [("NEW", None), ("NEW", "2000-01-01T00:00:00.000Z"), ("INTERESTED", None), ("IGNORED", None)]
        for i, (status, fetched) in enumerate(rows):
            self.connection.execute(
                "INSERT INTO leads (id, source, external_id, kind, title, description, url, status) "
                "VALUES (?, 'freelancer', ?, 'project', 't', 'd', 'https://x', ?)", (f"l{i}", str(i), status))
            if fetched:
                self.connection.execute("UPDATE leads SET fetched_at = ? WHERE id = ?", (fetched, f"l{i}"))
        self.assertEqual([x["id"] for x in list_leads(self.connection, view="new")], ["l0"])
        self.assertEqual([x["id"] for x in list_leads(self.connection, view="old")], ["l1"])
        self.assertEqual(lead_counts(self.connection),
                         {"all": 3, "new": 1, "old": 1, "interested": 1, "approved": 0, "proposal": 0, "ignored": 1})

    def test_ask_uses_real_facts_and_falls_back_without_llm(self):
        insert_job(self.connection, "a")
        prompts = []
        answer = desk.ask(self.connection, lambda p: prompts.append(p) or "Aku nemu 1.", "reno", "Hari ini dapat apa?")
        self.assertEqual(answer, {"answer": "Aku nemu 1.", "ai": True})
        self.assertIn("Lowongan baru 1", prompts[0])
        plain = desk.ask(self.connection, None, "reno", "Hari ini dapat apa?")
        self.assertFalse(plain["ai"])
        self.assertIn("1 lowongan baru", plain["answer"])
        with self.assertRaises(ValueError):
            desk.ask(self.connection, None, "reno", "   ")


class OfficeWorkDeskTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "app.db"
        self.connection = database.connect()
        apply_schema(self.connection)
        self.sent = []
        self.drafted = []

        class Drafts:
            def prepare(_, job_id):
                self.drafted.append(job_id)
                from bot_loker_wfh.drafts import DraftResult
                return DraftResult("created", job_id, "PENDING_APPROVAL")

        self.work = OfficeWork(hunters={}, draft_service_for=lambda c: Drafts(), form_assist_enabled=False,
            interval_seconds=3600, lock=threading.Lock(), notify=self.sent.append,
        )

    def tearDown(self):
        self.connection.close()
        self.tmp.cleanup()

    def test_requested_reports_go_to_telegram(self):
        result = self.work.request_reports(self.connection, "all")
        self.assertEqual(len(result["items"]), len(desk.EMPLOYEES))
        self.assertEqual(len(self.sent), 1)
        self.assertIn("Laporan kinerja tim", self.sent[0])
        with self.assertRaises(KeyError):
            self.work.request_reports(self.connection, "nobody")

    def test_sari_instruction_decides_which_candidates_get_drafted_first(self):
        insert_job(self.connection, "php", title="PHP Dev", score=0.9)
        insert_job(self.connection, "py", title="Python Dev", score=0.1)
        desk.set_instruction(self.connection, "sari", "python")
        self.work.draft_next(self.connection, limit=1)
        self.assertEqual(self.drafted, ["py"])

    def test_owner_records_company_reply(self):
        insert_job(self.connection, "j")
        self.connection.execute(
            "INSERT INTO applications (id, job_id, idempotency_key, status, cover_letter, cv_summary) "
            "VALUES ('app', 'j', 'k', 'SUBMITTED', 'L', 'CV')"
        )
        self.assertEqual([i["id"] for i in self.work.inbox(self.connection)["sent"]], ["app"])
        self.assertEqual(self.work.decide(self.connection, "app", "interview"), {"status": "INTERVIEW"})
        self.assertEqual(self.work.decide(self.connection, "app", "offer"), {"status": "OFFER"})
        self.assertEqual(self.work.inbox(self.connection)["sent"], [])


if __name__ == "__main__":
    unittest.main()


class ChatBodyParsingTest(unittest.TestCase):
    def test_json_with_trailing_done_and_sse_stream(self):
        from bot_loker_wfh.llm import _parse_chat_body
        tail = '{"choices": [{"message": {"content": "halo"}}]}data: [DONE]'
        self.assertEqual(_parse_chat_body(tail)["choices"][0]["message"]["content"], "halo")
        sse = 'data: {"choices": [{"delta": {"content": "ha"}}]}\ndata: {"choices": [{"delta": {"content": "lo"}}]}\ndata: [DONE]'
        self.assertEqual(_parse_chat_body(sse)["choices"][0]["message"]["content"], "halo")
