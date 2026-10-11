import io
import json
import threading
import unittest
from urllib.error import HTTPError

from bot_loker_wfh import database, freelancer_api, playwright_bid
from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.freelancer_api import FreelancerError, place_freelancer_bid
from bot_loker_wfh.office_work import OfficeWork

PROPOSAL = "Saya siap mengerjakan proyek ini dengan rapi dan tepat waktu. " * 3


def lead(connection, lead_id="a", source="freelancer", external_id="12345", url="https://www.freelancer.com/projects/x", terms=True):
    connection.execute(
        "INSERT INTO leads (id, source, external_id, kind, title, description, url, budget, status, proposal, bid_terms) "
        "VALUES (?, ?, ?, 'project', 'Build API', 'Need an API', ?, 'USD 250-750 | 19 bid', 'INTERESTED', ?, ?)",
        (lead_id, source, external_id, url, PROPOSAL,
         json.dumps({"amount": "500", "hourly_rate": "", "weekly_limit": "20", "duration_days": "14", "milestones": "a; b"}) if terms else None),
    )
    connection.commit()


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeApi:
    def __init__(self, bid_error=None):
        self.calls, self.bid_error = [], bid_error

    def __call__(self, request, timeout=None):
        body = json.loads(request.data) if request.data else None
        self.calls.append((request.get_method(), request.full_url.split("/api")[1], body, request.headers.get("Freelancer-oauth-v1")))
        if request.full_url.endswith("/users/0.1/self/"):
            return FakeResponse(json.dumps({"result": {"id": 777}}).encode())
        if self.bid_error:
            raise HTTPError(request.full_url, 400, "Bad", {}, io.BytesIO(json.dumps({"message": self.bid_error}).encode()))
        return FakeResponse(json.dumps({"status": "success", "result": {"id": 1}}).encode())


class FreelancerApiTest(unittest.TestCase):
    def setUp(self):
        self.connection = database.connect()
        apply_schema(self.connection)
        freelancer_api._bidder_ids.clear()

    def test_bid_is_sent_with_the_approved_values_and_marked_submitted(self):
        lead(self.connection)
        api = FakeApi()
        place_freelancer_bid(self.connection, "a", token="tok", opener=api)
        method, path, body, token = api.calls[-1]
        self.assertEqual((method, path, token), ("POST", "/projects/0.1/bids/", "tok"))
        self.assertEqual((body["project_id"], body["bidder_id"], body["amount"], body["period"], body["milestone_percentage"]), (12345, 777, 500.0, 14, 100))
        self.assertEqual(body["description"], PROPOSAL.strip())
        self.assertEqual(self.connection.execute("SELECT status FROM leads WHERE id='a'").fetchone()[0], "SUBMITTED")

    def test_platform_rejection_is_reported_and_status_stays_open(self):
        lead(self.connection)
        with self.assertRaises(FreelancerError) as raised:
            place_freelancer_bid(self.connection, "a", token="tok", opener=FakeApi("You have insufficient bids"))
        self.assertIn("insufficient bids", str(raised.exception))
        self.assertNotIn("tok", str(raised.exception))
        self.assertEqual(self.connection.execute("SELECT status FROM leads WHERE id='a'").fetchone()[0], "INTERESTED")

    def test_missing_price_or_wrong_platform_is_refused_without_calling_the_api(self):
        lead(self.connection, "noterms", terms=False)
        lead(self.connection, "other", source="projects.co.id", external_id="x1")
        api = FakeApi()
        for lead_id in ("noterms", "other"):
            with self.assertRaises(FreelancerError):
                place_freelancer_bid(self.connection, lead_id, token="tok", opener=api)
        self.assertEqual(api.calls, [])


class ApproveViaApiTest(unittest.TestCase):
    def setUp(self):
        self.connection = database.connect()
        apply_schema(self.connection)
        lead(self.connection)
        self.sent = []

    def work(self, bid):
        return OfficeWork(hunters={}, draft_service_for=None, form_assist_enabled=False, interval_seconds=1,
                          lock=threading.Lock(), freelancer_bid=bid, spawn=lambda *a, **k: self.fail("no browser expected"))

    def test_approve_on_freelancer_uses_the_api_not_a_browser(self):
        def bid(connection, lead_id):
            self.sent.append(lead_id)
            connection.execute("UPDATE leads SET status = 'SUBMITTED' WHERE id = ?", (lead_id,))
        result = self.work(bid).lead_action(self.connection, "a", "approve", {})
        self.assertEqual((result["mode"], result["status"], self.sent), ("api", "SUBMITTED", ["a"]))

    def test_api_failure_reaches_the_owner_and_reopens_the_lead(self):
        def bid(connection, lead_id):
            raise FreelancerError("Freelancer menolak bid: sudah pernah menawar")
        with self.assertRaises(ValueError) as raised:
            self.work(bid).lead_action(self.connection, "a", "approve", {})
        self.assertIn("sudah pernah menawar", str(raised.exception))
        self.assertEqual(self.connection.execute("SELECT status FROM leads WHERE id='a'").fetchone()[0], "INTERESTED")

    def test_leads_listing_tells_the_web_which_sources_need_a_tab(self):
        sources = self.work(lambda c, i: None).leads(self.connection, None)["tab_sources"]
        self.assertNotIn("freelancer", sources)
        self.assertNotIn("projects.co.id", sources)
        self.assertIn("freelancer", self.work(None).leads(self.connection, None)["tab_sources"])


class FieldMatchingTest(unittest.TestCase):
    def test_amount_days_and_proposal_are_told_apart(self):
        items = [(0, "input", "harga penawaran (rp)", ""), (1, "input", "lama pengerjaan (hari)", ""), (2, "textarea", "deskripsi proposal", "")]
        self.assertEqual(playwright_bid.match_fields(items), {"proposal": 2, "amount": 0, "days": 1})

    def test_block_text_is_only_a_fallback(self):
        items = [(0, "input", "", "harga anda"), (1, "input", "x", "hari"), (2, "textarea", "", "")]
        self.assertEqual(playwright_bid.match_fields(items)["amount"], 0)


class ChromeProfileImportTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.source, self.dest = base / "User Data", base / "bot-profile"
        (self.source / "Default" / "Network").mkdir(parents=True)
        (self.source / "Default" / "Cache").mkdir()
        (self.source / "Default" / "Network" / "Cookies").write_bytes(b"cookies")
        (self.source / "Default" / "Cache" / "big").write_bytes(b"x" * 10)
        (self.source / "Local State").write_text("{}")

    def test_copies_logins_but_not_caches(self):
        message = playwright_bid.import_chrome_profile("Default", source=self.source, dest=self.dest, running=lambda: False)
        self.assertIn("disalin", message)
        self.assertTrue((self.dest / "Local State").is_file())
        self.assertEqual((self.dest / "Default" / "Network" / "Cookies").read_bytes(), b"cookies")
        self.assertFalse((self.dest / "Default" / "Cache").exists())
        self.assertTrue(playwright_bid.profile_ready(self.dest, "Default"))

    def test_refuses_while_chrome_is_running_and_for_unknown_profiles(self):
        with self.assertRaises(playwright_bid.ProfileImportError):
            playwright_bid.import_chrome_profile("Default", source=self.source, dest=self.dest, running=lambda: True)
        with self.assertRaises(playwright_bid.ProfileImportError):
            playwright_bid.import_chrome_profile("Profile 9", source=self.source, dest=self.dest, running=lambda: False)
        self.assertFalse(self.dest.exists())


FORM = """
<form onsubmit="event.preventDefault(); document.body.insertAdjacentHTML('beforeend','<p>Penawaran berhasil diajukan</p>');">
  <label for="p">Harga penawaran (Rp)</label><input id="p" type="text">
  <label for="d">Lama pengerjaan (hari)</label><input id="d" type="text">
  <label for="t">Deskripsi proposal</label><textarea id="t"></textarea>
  <button type="submit">Ajukan Penawaran</button>
</form>
"""


class BrowserFormTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
            cls.playwright = sync_playwright().start()
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except Exception as error:  # playwright or chromium not installed
            raise unittest.SkipTest(f"playwright/chromium unavailable: {error}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def test_form_is_filled_and_the_submit_button_pressed(self):
        page = self.browser.new_page()
        page.set_content(FORM)
        result = playwright_bid._fill_and_submit(page, amount="500000", days="10", proposal="isi proposal", login_wait=0, sleep=lambda s: None)
        self.assertTrue(result.submitted, result.message)
        self.assertEqual(page.input_value("#p"), "500000")
        self.assertEqual(page.input_value("#d"), "10")
        self.assertEqual(page.input_value("#t"), "isi proposal")

    def test_captcha_stops_before_any_click(self):
        page = self.browser.new_page()
        page.set_content(FORM + "<div class='g-recaptcha'>recaptcha</div>")
        result = playwright_bid._fill_and_submit(page, amount="1", days="1", proposal="x", login_wait=0, sleep=lambda s: None)
        self.assertEqual(result.status, "captcha")
        self.assertNotIn("berhasil", page.inner_text("body"))

    def test_page_without_a_bid_form_is_reported_not_guessed(self):
        page = self.browser.new_page()
        page.set_content("<p>Silakan login dengan password Anda</p>")
        result = playwright_bid._fill_and_submit(page, amount="1", days="1", proposal="x", login_wait=0, sleep=lambda s: None)
        self.assertIn(result.status, ("login_timeout", "missing_fields"))


if __name__ == "__main__":
    unittest.main()
