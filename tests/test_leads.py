import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from bot_loker_wfh.bot import BotRunner
from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.drafts import DraftService
from bot_loker_wfh.leads import (
    FreelancerFetcher,
    Lead,
    LeadService,
    ProjectsCoIdFetcher,
    TelegramChannelFetcher,
    classify,
)
from bot_loker_wfh.pipeline import JobPipeline

from test_bot_pipeline import PROFILE
from test_bot_runner import OWNER, STRANGER, FakeClient, FakeScheduler, callback_update, message_update

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def iso(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat()


class ClassifyTest(unittest.TestCase):
    def test_one_strong_term_is_enough_and_hyphens_are_ignored(self):
        self.assertEqual(classify("Full-Stack dev needed", "")[0], "project")
        self.assertEqual(classify("Fix my Laravel site", "")[0], "project")

    def test_weak_terms_need_two_matches(self):
        self.assertIsNone(classify("Hire a developer", "for logo design")[0])
        self.assertEqual(classify("Developer for API", "")[0], "project")

    def test_irrelevant_lead_is_dropped(self):
        self.assertEqual(classify("Translate my book", "English to French"), (None, 0.0))

    def test_profile_skills_count_as_strong_terms(self):
        self.assertIsNone(classify("Need Tailwind CSS help", "")[0])
        self.assertEqual(classify("Need Tailwind CSS help", "", ("Tailwind CSS",))[0], "project")

    def test_source_code_is_only_a_sales_lead_when_someone_wants_to_buy_code(self):
        deliverable = classify("Laravel shop", "You must hand over the full source code.")
        buyer = classify("Laravel shop", "Looking for source code of a delivery app.")
        by_title = classify("Source code for booking app", "PHP")
        indonesian = classify("WTB aplikasi jadi", "sistem informasi sekolah")

        self.assertEqual(deliverable[0], "project")
        self.assertEqual(buyer[0], "source_code")
        self.assertEqual(by_title[0], "source_code")
        self.assertEqual(indonesian[0], "source_code")


def freelancer_project(number, **overrides):
    project = {
        "id": number,
        "title": f"Laravel app {number}",
        "status": "active",
        "seo_url": f"php/Laravel-app-{number}",
        "description": "Build a Laravel dashboard.",
        "currency": {"code": "USD"},
        "budget": {"minimum": 250.0, "maximum": 750.0},
        "type": "fixed",
        "bid_stats": {"bid_count": 12},
        "time_submitted": int((NOW - timedelta(hours=5)).timestamp()),
    }
    project.update(overrides)
    return project


class SourceFetcherTest(unittest.TestCase):
    def test_freelancer_normalizes_dedupes_and_skips_unusable_projects(self):
        payloads = {
            "a": {"result": {"projects": [
                freelancer_project(1),
                freelancer_project(2, deleted=True),
                freelancer_project(3, status="closed"),
                freelancer_project(4, type="hourly", budget={"minimum": 15, "maximum": 25}),
            ]}},
            "b": {"result": {"projects": [freelancer_project(1)]}},
        }
        fetcher = FreelancerFetcher(fetch_json=payloads.__getitem__, queries=("a", "b"), delay_seconds=0)

        leads = fetcher.fetch()

        self.assertEqual([lead.external_id for lead in leads], ["1", "4"])
        self.assertEqual(leads[0].url, "https://www.freelancer.com/projects/php/Laravel-app-1")
        self.assertEqual(leads[0].budget, "USD 250-750 | 12 bid")
        self.assertEqual(leads[1].budget, "USD 15-25/hour | 12 bid")
        self.assertTrue(leads[0].posted_at.startswith("2026-09-19T07:00"))

    def test_projects_co_id_paginates_and_builds_absolute_urls(self):
        def item(number):
            return {
                "project_id": f"p{number}",
                "title": f"Buat Website {number}",
                "short_description": "  Butuh   programmer  ",
                "budget_range_str": "Rp 1,000,000 - 2,000,000",
                "published_date": "2026-09-18 08:00:00",
                "bid_count": 3,
                "buttons": [
                    {"text": "Place New Bid", "url": "/bid"},
                    {"text": "View", "url": f"/public/browse_projects/view/p{number}/x"},
                ],
            }

        pages = {
            1: {"items": [item(1)], "paging": {"total_pages": 2}},
            2: {"items": [item(2), {"title": "no id"}], "paging": {"total_pages": 2}},
        }
        leads = ProjectsCoIdFetcher(fetch_json=pages.__getitem__, delay_seconds=0).fetch()

        self.assertEqual([lead.external_id for lead in leads], ["p1", "p2"])
        self.assertEqual(leads[0].url, "https://projects.co.id/public/browse_projects/view/p1/x")
        self.assertEqual(leads[0].description, "Butuh programmer")
        self.assertEqual(leads[0].posted_at, "2026-09-18T08:00:00+07:00")
        self.assertEqual(leads[0].budget, "Rp 1,000,000 - 2,000,000 | 3 bid")

    def test_telegram_channel_parsing_and_name_validation(self):
        page = (
            '<div class="tgme_widget_message_wrap js-widget_message_wrap">'
            '<div class="tgme_widget_message" data-post="infoproyek/42">'
            '<div class="tgme_widget_message_text js-message_text" dir="auto">'
            "JUAL source code <b>Laravel</b> POS<br/>hubungi &amp; DM</div>"
            '<time datetime="2026-09-19T10:00:00+00:00" class="time">x</time></div></div>'
            '<div class="tgme_widget_message_wrap"><div data-post="infoproyek/43">'
            '<time datetime="2026-09-19T11:00:00+00:00"></time></div></div>'
        )
        fetcher = TelegramChannelFetcher(["@infoproyek"], fetch_html=lambda channel: page, delay_seconds=0)

        leads = fetcher.fetch()

        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0].external_id, "infoproyek/42")
        self.assertEqual(leads[0].url, "https://t.me/infoproyek/42")
        self.assertEqual(leads[0].description, "JUAL source code Laravel POS hubungi & DM")
        with self.assertRaises(ValueError):
            TelegramChannelFetcher(["bad/name?x=1"])


class StaticFetcher:
    def __init__(self, source, leads=None, error=None):
        self.source = source
        self.leads = leads or []
        self.error = error

    def fetch(self):
        if self.error:
            raise self.error
        return self.leads


def lead(number, *, title="Laravel dashboard", description="", days_ago=1, source="freelancer"):
    return Lead(source, str(number), title, description, f"https://example.com/{number}",
                budget="USD 100", posted_at=iso(days_ago))


class LeadServiceTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)

    def service(self, *fetchers):
        return LeadService(self.connection, PROFILE, fetchers=list(fetchers), now=lambda: NOW)

    def test_stores_only_recent_relevant_new_leads(self):
        service = self.service(StaticFetcher("freelancer", [
            lead(1),
            lead(2, days_ago=10),                       # too old
            lead(3, title="Translate my book"),         # irrelevant
            Lead("freelancer", "4", "Laravel", "", "u"),  # no date
        ]))

        self.assertEqual(service.collect(), {"freelancer": 1})
        self.assertEqual(service.collect(), {"freelancer": 0})   # deduped
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM leads").fetchone()[0], 1)

    def test_a_failing_source_does_not_stop_the_others(self):
        service = self.service(
            StaticFetcher("freelancer", error=OSError("down")),
            StaticFetcher("projects.co.id", [lead(1, source="projects.co.id")]),
        )
        self.assertEqual(service.collect(), {"projects.co.id": 1})

    def test_notification_order_message_and_status_changes(self):
        service = self.service(StaticFetcher("freelancer", [
            lead(1, title="Laravel"),
            lead(2, title="Laravel React NestJS Flutter"),
        ]))
        service.collect()

        ids = service.unnotified_ids(5)
        self.assertEqual(len(ids), 2)
        first = service.message(ids[0], OWNER)
        self.assertIn("NestJS", first.text)             # higher score first
        self.assertIn("Proyek dicari developer", first.text)
        self.assertEqual(
            [button.callback_data for button in first.inline_keyboard[0]],
            [f"lead:{ids[0]}:INTERESTED", f"lead:{ids[0]}:IGNORED"],
        )
        self.assertLessEqual(len(first.inline_keyboard[0][0].callback_data.encode()), 64)

        service.mark_notified(ids[0])
        self.assertEqual(service.unnotified_ids(5), [ids[1]])
        self.assertTrue(service.set_status(ids[0], "INTERESTED"))
        self.assertFalse(service.set_status("missing", "IGNORED"))
        with self.assertRaises(ValueError):
            service.set_status(ids[0], "DELETED")
        self.assertIn("[INTERESTED]", service.list_text().split("\n\n")[1])
        service.set_status(ids[1], "IGNORED")
        self.assertNotIn("IGNORED", service.list_text())


class BotLeadTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)
        self.client = FakeClient()
        self.leads = LeadService(
            self.connection, PROFILE,
            fetchers=[StaticFetcher("freelancer", [lead(number) for number in range(1, 8)])],
            now=lambda: NOW,
        )
        self.scheduler = FakeScheduler()
        self.runner = BotRunner(
            self.connection,
            client=self.client,
            allowed_chat_ids=frozenset({OWNER}),
            draft_service=DraftService(self.connection, PROFILE),
            pipeline=JobPipeline(self.connection, PROFILE),
            scheduler=self.scheduler,
            interval_seconds=4 * 3600,
            lead_service=self.leads,
        )

    def lead_status(self, lead_id):
        return self.connection.execute("SELECT status FROM leads WHERE id = ?", (lead_id,)).fetchone()[0]

    def test_cycle_collects_and_notifies_leads_in_capped_batches(self):
        summary = self.runner.run_cycle()

        self.assertEqual(summary["lead_new"], 7)
        self.assertEqual(summary["lead_notified"], 5)
        self.assertEqual(self.runner.notify_leads(), 2)
        self.assertEqual(self.runner.notify_leads(), 0)
        self.assertEqual(len(self.client.messages), 7)

    def test_lead_buttons_set_status_and_reject_strangers_and_bad_input(self):
        self.leads.collect()
        lead_id = self.leads.unnotified_ids(1)[0]

        self.runner.handle_update(callback_update(OWNER, f"lead:{lead_id}:INTERESTED"))
        self.assertEqual(self.lead_status(lead_id), "INTERESTED")
        self.runner.handle_update(callback_update(OWNER, f"lead:{lead_id}:IGNORED"))
        self.assertEqual(self.lead_status(lead_id), "IGNORED")

        self.runner.handle_update(callback_update(OWNER, f"lead:{lead_id}:DELETE"))
        self.assertEqual(self.client.answers[-1][1], "Invalid request.")
        self.runner.handle_update(callback_update(OWNER, "lead:missing:IGNORED"))
        self.assertEqual(self.client.answers[-1][1], "Lead tidak ditemukan.")

        self.runner.handle_update(callback_update(STRANGER, f"lead:{lead_id}:INTERESTED"))
        self.assertEqual(self.client.answers[-1][1], "Unauthorized chat.")
        self.assertEqual(self.lead_status(lead_id), "IGNORED")

    def test_lead_command_lists_and_help_mentions_it(self):
        self.runner.handle_update(message_update(OWNER, "/lead"))
        self.assertEqual(self.client.texts[-1][1], "Belum ada lead.")

        self.leads.collect()
        self.runner.handle_update(message_update(OWNER, "/lead"))
        self.assertIn("Laravel dashboard", self.client.texts[-1][1])
        self.runner.handle_update(message_update(OWNER, "/help"))
        self.assertIn("/lead", self.client.texts[-1][1])


if __name__ == "__main__":
    unittest.main()
