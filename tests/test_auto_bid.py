import unittest
from unittest.mock import Mock

from bot_loker_wfh import database
from bot_loker_wfh.auto_bid import candidates, config, run_auto_bids
from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.settings_store import set_setting

PROPOSAL = "Saya siap mengerjakan proyek ini dengan rapi dan tepat waktu. " * 3


class AutoBidTest(unittest.TestCase):
    def setUp(self):
        self.connection = database.connect()
        apply_schema(self.connection)
        self.sent, self.notes = [], []

    def lead(self, lead_id, *, score=0.9, budget="USD 250-750 | 10 bid", source="freelancer", proposal=PROPOSAL, age_hours=1, status="NEW"):
        self.connection.execute(
            "INSERT INTO leads (id, source, external_id, kind, title, description, url, budget, status, proposal, score, posted_at) "
            "VALUES (?, ?, ?, 'project', ?, 'd', 'https://www.freelancer.com/projects/x', ?, ?, ?, ?, "
            "utc_now_iso(?))",
            (lead_id, source, lead_id, f"Project {lead_id}", budget, status, proposal, score, f"-{age_hours} hours"),
        )
        self.connection.commit()

    def place(self, connection, lead_id):
        self.sent.append(lead_id)
        connection.execute("UPDATE leads SET status = 'SUBMITTED', bid_submitted_at = utc_now_iso() WHERE id = ?", (lead_id,))

    def enable(self, **extra):
        set_setting(self.connection, "auto_bid_enabled", "1")
        for key, value in extra.items():
            set_setting(self.connection, key, str(value))

    def bid_pass(self, place=None):
        return run_auto_bids(self.connection, place or self.place, self.notes.append)

    def test_off_by_default_sends_nothing(self):
        self.lead("a")
        self.assertEqual(self.bid_pass()["skipped"], "owner_approval_required")
        self.assertEqual(self.sent, [])

    def test_legacy_enabled_switch_never_sends_without_owner_approval(self):
        self.enable()
        self.lead("draft")
        place = Mock()
        reconcile = Mock()
        result = run_auto_bids(self.connection, place, self.notes.append, reconcile)
        row = self.connection.execute("SELECT status, bid_auto, bid_submitted_at FROM leads WHERE id='draft'").fetchone()
        self.assertEqual(result, {"sent": 0, "skipped": "owner_approval_required"})
        self.assertEqual(tuple(row), ("NEW", 0, None))
        place.assert_not_called()
        reconcile.assert_not_called()
        self.assertEqual(self.notes, [])

    def test_guard_rails_filter_candidates(self):
        self.enable()
        self.lead("low", score=0.5)
        self.lead("old", age_hours=72)
        self.lead("crowded", budget="USD 250-750 | 90 bid")
        self.lead("nobudget", budget="Budget n/a")
        self.lead("other", source="projects.co.id")
        self.lead("short", proposal="tiny")
        self.lead("ignored", status="IGNORED")
        self.lead("ok")
        self.assertEqual([i for i, _ in candidates(self.connection, config(self.connection), 10)], ["ok"])

    def test_projects_the_account_cannot_bid_on_are_not_even_tried(self):
        self.enable()
        self.lead("big", budget="USD 100,000-? | 5 bid")
        self.lead("edge", budget="USD 2500-5000 | 5 bid")
        self.lead("inr", budget="INR 12,500-37,500 | 5 bid")
        self.lead("small", budget="USD 250-750 | 5 bid")
        self.assertEqual({i for i, _ in candidates(self.connection, config(self.connection), 10)}, {"inr", "small"})

    def test_long_drafts_are_split_not_truncated(self):
        from bot_loker_wfh.auto_bid import split_text

        text = "\n".join(f"baris {i} " + "x" * 90 for i in range(120))
        parts = split_text(text)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(p) <= 3900 for p in parts))
        self.assertEqual("\n".join(parts), text)
        self.assertEqual(split_text("pendek"), ["pendek"])


if __name__ == "__main__":
    unittest.main()


class FreelanceManagerReportTest(unittest.TestCase):
    """Mira, the freelance division manager, reports what the whole division did."""

    def setUp(self):
        self.connection = database.connect()
        apply_schema(self.connection)

    def lead(self, lead_id, source="freelancer", **cols):
        self.connection.execute(
            "INSERT INTO leads (id, source, external_id, kind, title, description, url, budget, proposal, status) "
            "VALUES (?, ?, ?, 'project', ?, 'd', 'https://x', 'USD 250-750 | 10 bid', ?, ?)",
            (lead_id, source, lead_id, f"Project {lead_id}", cols.get("proposal"), cols.get("status", "NEW")),
        )
        for column in ("bid_submitted_at", "bid_auto", "bid_error", "bid_claimed_at", "bid_terms"):
            if column in cols:
                self.connection.execute(f"UPDATE leads SET {column} = ? WHERE id = ?", (cols[column], lead_id))
        self.connection.commit()

    def test_manager_is_an_employee_with_a_division_report(self):
        from bot_loker_wfh import office_desk as desk
        self.assertIn("mira", desk.EMPLOYEES)
        self.lead("sent", proposal=PROPOSAL, status="SUBMITTED", bid_auto=1, bid_submitted_at="2099-01-01T00:00:00.000Z")
        self.lead("drafted", proposal=PROPOSAL, status="INTERESTED")
        self.lead("refused", proposal=PROPOSAL, status="INTERESTED", bid_error="Freelancer menolak bid: sudah pernah menawar",
                  bid_claimed_at="2099-01-01T00:00:00.000Z")
        self.lead("plain", source="projects.co.id")
        report = desk.measure(self.connection, "mira", 24)
        metrics = {label: value for _, label, value in report["metrics"]}
        self.assertEqual((metrics["Proyek baru"], metrics["Draf bid"], metrics["Bid terkirim"], metrics["Otomatis"], metrics["Ditolak"]), (4, 3, 1, 1, 1))
        text = "\n".join(report["lines"])
        for name in ("Lido", "Nara", "Tama", "Bimo"):
            self.assertIn(f"• {name}:", text)
        self.assertIn("sudah pernah menawar", text)
        self.assertIn("Auto-bid mati", text)
        self.assertIn("Project sent", text)
        self.assertTrue(0 <= report["score"] <= 1)

    def test_manager_report_can_be_saved_like_any_employee_report(self):
        from bot_loker_wfh import office_desk as desk
        saved = desk.create_report(self.connection, "mira")
        self.assertEqual(saved["employee"], "mira")
        self.assertTrue(saved["lines"])
        self.assertEqual(desk.profile(self.connection, "mira")["periods"].keys(), desk.profile(self.connection, "lido")["periods"].keys())


class RunSoonTest(unittest.TestCase):
    def test_owner_can_wake_the_work_loop_for_an_immediate_cycle(self):
        import threading
        from bot_loker_wfh.office_work import OfficeWork
        work = OfficeWork(hunters={}, draft_service_for=None, form_assist_enabled=False, interval_seconds=3600, lock=threading.Lock())
        work.next_at = 10**9
        work.run_soon()
        self.assertIsNone(work.next_at)
        self.assertTrue(work._wake.is_set())
