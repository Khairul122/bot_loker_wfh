import io
import json
import logging
import sqlite3
import unittest

from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.scheduler import JobScheduler


class SchedulerTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)

    def tearDown(self):
        self.connection.close()

    def test_default_interval_is_at_least_four_hours(self):
        scheduler = JobScheduler(self.connection, fetchers={})

        self.assertGreaterEqual(scheduler.interval_seconds(), 4 * 60 * 60)

    def test_interval_below_minimum_is_clamped(self):
        scheduler = JobScheduler(self.connection, fetchers={}, interval_hours=0.001)

        self.assertGreaterEqual(scheduler.interval_seconds(), 5 * 60)

    def test_interval_hours_can_be_read_from_database(self):
        from bot_loker_wfh.settings_store import set_scrape_interval_hours

        set_scrape_interval_hours(self.connection, 0.5)
        scheduler = JobScheduler(
            self.connection,
            fetchers={},
            interval_hours=lambda: __import__(
                "bot_loker_wfh.settings_store", fromlist=["get_scrape_interval_hours"]
            ).get_scrape_interval_hours(self.connection),
        )

        self.assertEqual(scheduler.interval_seconds(), 30 * 60)

    def test_one_shot_runs_remoteok_and_remotive(self):
        calls = []

        scheduler = JobScheduler(
            self.connection,
            fetchers={
                "remoteok": lambda: calls.append("remoteok") or 2,
                "remotive": lambda: calls.append("remotive") or 3,
            },
        )

        result = scheduler.run_once()

        self.assertEqual(calls, ["remoteok", "remotive"])
        self.assertEqual(result, {"remoteok": 2, "remotive": 3})

    def test_logs_only_source_and_insert_count(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger("scheduler-test")
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        scheduler = JobScheduler(
            self.connection,
            fetchers={"remoteok": lambda: 1},
            logger=logger,
        )
        scheduler.run_once()

        record = json.loads(stream.getvalue())
        self.assertEqual(record["event"], "fetch_complete")
        self.assertEqual(record["source"], "remoteok")
        self.assertEqual(record["status"], "success")
        self.assertEqual(record["duration_ms"], 0)
        self.assertEqual(record["inserted_count"], 1)
        self.assertNotIn("description", record)
        self.assertNotIn("cover_letter", record)


if __name__ == "__main__":
    unittest.main()
