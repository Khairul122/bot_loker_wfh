import sqlite3
import unittest
from unittest import mock

from bot_loker_wfh import settings_store
from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.settings_store import (
    DEFAULTS,
    SupabaseUnavailable,
    cloud_configured,
    fetch_cloud_settings,
    get_scrape_interval_hours,
    get_setting,
    set_scrape_interval_hours,
    set_setting,
    store_cloud_setting,
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


class CloudSettingsTest(unittest.TestCase):
    """Supabase is authoritative when configured; mocked so no network is touched."""

    def test_cloud_configured_reflects_database_module(self):
        with mock.patch.object(settings_store.database, "supabase_configured", lambda: True, create=True):
            self.assertTrue(cloud_configured())
        with mock.patch.object(settings_store.database, "supabase_configured", lambda: False, create=True):
            self.assertFalse(cloud_configured())

    def test_missing_backend_reports_not_configured(self):
        with mock.patch.object(settings_store.database, "supabase_configured", None, create=True):
            self.assertFalse(cloud_configured())

    def test_fetch_passes_table_and_parses_rows(self):
        rows = [{"key": "scrape_interval_hours", "value": "8"}, {"key": "llm_provider", "value": "9router"}]
        request = mock.Mock(return_value=rows)
        with mock.patch.object(settings_store.database, "supabase_request", request, create=True):
            self.assertEqual(fetch_cloud_settings(), {"scrape_interval_hours": "8", "llm_provider": "9router"})
        request.assert_called_once_with("app_settings", method="GET", query={"select": "key,value"})

    def test_fetch_propagates_backend_failure(self):
        request = mock.Mock(side_effect=SupabaseUnavailable("down"))
        with mock.patch.object(settings_store.database, "supabase_request", request, create=True):
            with self.assertRaises(settings_store.cloud_error_types()):
                fetch_cloud_settings()

    def test_store_upserts_key_value(self):
        request = mock.Mock(return_value=[{"key": "llm_provider", "value": "9router"}])
        with mock.patch.object(settings_store.database, "supabase_request", request, create=True):
            store_cloud_setting("llm_provider", "9router")
        request.assert_called_once_with("app_settings", method="POST",
                                        data={"key": "llm_provider", "value": "9router"})

    def test_missing_backend_request_raises_unavailable(self):
        with mock.patch.object(settings_store.database, "supabase_request", None, create=True):
            with self.assertRaises(SupabaseUnavailable):
                fetch_cloud_settings()

    def test_cloud_error_types_include_database_exception(self):
        class Boom(Exception):
            pass

        with mock.patch.object(settings_store.database, "SupabaseUnavailable", Boom, create=True):
            self.assertIn(Boom, settings_store.cloud_error_types())
            self.assertIn(SupabaseUnavailable, settings_store.cloud_error_types())


if __name__ == "__main__":
    unittest.main()
