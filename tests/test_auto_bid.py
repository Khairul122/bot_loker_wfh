import unittest

from bot_loker_wfh import database
from bot_loker_wfh.auto_bid import candidates, config, run_auto_bids
from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.freelancer_api import FreelancerError
from bot_loker_wfh.settings_store import get_setting, set_setting

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
        self.assertEqual(self.bid_pass()["skipped"], "off")
        self.assertEqual(self.sent, [])

    def test_sends_best_scored_fresh_projects_and_records_the_audit_trail(self):
        self.enable()
        self.lead("good", score=0.95)
        self.lead("better", score=1.0)
        result = self.bid_pass()
        self.assertEqual((result["sent"], self.sent), (2, ["better", "good"]))
        row = self.connection.execute("SELECT status, bid_auto, bid_submitted_at FROM leads WHERE id='good'").fetchone()
        self.assertEqual((row[0], row[1]), ("SUBMITTED", 1))
        self.assertIsNotNone(row[2])
        self.assertEqual(len(self.notes), 2)

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

    def test_daily_cap_counts_the_last_24_hours(self):
        self.enable(auto_bid_max_per_day=2)
        for lead_id in ("a", "b", "c", "d"):
            self.lead(lead_id)
        self.assertEqual(self.bid_pass()["sent"], 2)
        self.assertEqual(self.bid_pass()["skipped"], "daily_cap")
        self.assertEqual(len(self.sent), 2)

    def test_a_refusal_stops_the_pass_and_the_lead_is_not_retried(self):
        self.enable()
        self.lead("a", score=1.0)
        self.lead("b", score=0.9)

        def refuse(connection, lead_id):
            raise FreelancerError("Freelancer menolak bid: sudah pernah menawar")

        result = self.bid_pass(refuse)
        self.assertEqual(result["sent"], 0)
        self.assertIn("sudah pernah menawar", result["error"])
        self.assertEqual(self.connection.execute("SELECT status FROM leads WHERE id='a'").fetchone()[0], "INTERESTED")
        self.assertEqual(get_setting(self.connection, "auto_bid_enabled"), "1")  # not fatal: stays on
        self.sent.clear()
        self.bid_pass()  # next pass skips the errored lead and bids on the other one
        self.assertEqual(self.sent, ["b"])

    def test_token_or_quota_trouble_switches_auto_bid_off_and_tells_the_owner(self):
        self.enable()
        self.lead("a")

        def quota(connection, lead_id):
            raise FreelancerError("Freelancer menolak bid: insufficient bids left")

        self.bid_pass(quota)
        self.assertEqual(get_setting(self.connection, "auto_bid_enabled"), "0")
        self.assertTrue(any("dimatikan" in note for note in self.notes))


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
