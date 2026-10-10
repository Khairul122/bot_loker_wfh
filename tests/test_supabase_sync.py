import unittest
from unittest import mock

from bot_loker_wfh import database as db


class SupabaseRequestTest(unittest.TestCase):
    def test_key_read_lazily_after_import(self):
        with mock.patch.dict("os.environ", {"SUPABASE_SERVICE_ROLE_KEY": "late"}):
            self.assertTrue(db.supabase_configured())

    def test_not_configured_raises(self):
        with mock.patch.dict("os.environ", {"SUPABASE_SERVICE_ROLE_KEY": "", "SUPABASE_SERVICE_KEY": "", "SUPABASE_KEY": ""}):
            self.assertFalse(db.supabase_configured())
            with self.assertRaises(db.SupabaseUnavailable):
                db.supabase_request("app_settings")

    def test_get_parses_json_and_sends_key(self):
        with mock.patch.dict("os.environ", {"SUPABASE_SERVICE_ROLE_KEY": "svc"}), \
                mock.patch("bot_loker_wfh.database.urllib.request.urlopen") as opener:
            opener.return_value.__enter__.return_value.read.return_value = b'[{"key":"a","value":"b"}]'
            out = db.supabase_request("app_settings", query={"select": "key,value"})
            self.assertEqual(out, [{"key": "a", "value": "b"}])
            request = opener.call_args[0][0]
            self.assertEqual(request.headers["Apikey"], "svc")
            self.assertIn("select=key", request.full_url)

    def test_failure_raises(self):
        with mock.patch.dict("os.environ", {"SUPABASE_SERVICE_ROLE_KEY": "svc"}), \
                mock.patch("bot_loker_wfh.database.urllib.request.urlopen", side_effect=OSError("down")):
            with self.assertRaises(db.SupabaseUnavailable):
                db.supabase_request("app_settings")

    def test_best_effort_sync_swallows_errors(self):
        with mock.patch.dict("os.environ", {"SUPABASE_SERVICE_ROLE_KEY": "", "SUPABASE_SERVICE_KEY": "", "SUPABASE_KEY": ""}):
            self.assertIsNone(db.sync_to_supabase("app_settings", {"key": "a"}))


if __name__ == "__main__":
    unittest.main()



class MeetingSyncTest(unittest.TestCase):
    def test_meeting_writes_are_mirrored(self):
        import sqlite3
        from bot_loker_wfh import meeting_runtime as mr
        conn = sqlite3.connect(":memory:")
        mr.ensure_schema(conn)
        with mock.patch.object(mr, "sync_to_supabase") as sync:
            m = mr.create_meeting(conn, "Topik", "2026-10-11T00:00:00Z", ["cora"])
            mr.set_status(conn, m["id"], "active")
            mr.add_event(conn, m["id"], "cora", "note", "halo")
        tables = [c.args[0] for c in sync.call_args_list]
        self.assertEqual(tables, ["meetings", "meeting_participants", "meetings", "meeting_events"])
