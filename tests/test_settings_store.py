import sqlite3
import unittest

from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.settings_store import (
    DEFAULTS,
    get_scrape_interval_hours,
    get_setting,
    set_scrape_interval_hours,
    set_setting,
)


class SettingsStoreTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)

    def tearDown(self):
        self.connection.close()

    def test_default_scrape_interval_matches_migration(self):
        self.assertEqual(get_setting(self.connection, "scrape_interval_hours"), "4")

    def test_roundtrip_set_get(self):
        set_scrape_interval_hours(self.connection, 0.5)

        self.assertEqual(get_scrape_interval_hours(self.connection), 0.5)

    def test_update_overwrites_existing_row(self):
        set_setting(self.connection, "scrape_interval_hours", "2")
        set_setting(self.connection, "scrape_interval_hours", "6")

        self.assertEqual(get_scrape_interval_hours(self.connection), 6.0)

    def test_interval_below_lower_bound_is_rejected(self):
        _, lower = DEFAULTS["scrape_interval_hours"]

        with self.assertRaises(ValueError):
            set_setting(self.connection, "scrape_interval_hours", str(lower - 0.01))

    def test_unknown_key_is_rejected(self):
        with self.assertRaises(KeyError):
            set_setting(self.connection, "not_a_real_key", "1")


if __name__ == "__main__":
    unittest.main()
