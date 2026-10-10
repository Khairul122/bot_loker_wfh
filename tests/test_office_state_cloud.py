import sqlite3
import unittest
from unittest import mock

from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.office_state import load_state_cloud, save_state


class OfficeStateCloudTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)

    def tearDown(self):
        self.connection.close()

    def test_load_prefers_cloud_last_position(self):
        save_state(self.connection, {"owner": {"x": 1, "y": 0, "z": 2, "yaw": 0}})
        cloud = [{"character_id": "owner", "role": "owner", "x": 9.0, "y": 0.0, "z": 8.0, "yaw": 1.0}]
        with mock.patch("bot_loker_wfh.office_state.supabase_configured", return_value=True), \
                mock.patch("bot_loker_wfh.office_state.supabase_request", return_value=cloud) as request:
            state = load_state_cloud(self.connection)
        self.assertEqual(state["owner"]["x"], 9.0)
        self.assertEqual(request.call_args[0][0], "office_character_state")

    def test_load_falls_back_to_local_when_cloud_empty(self):
        save_state(self.connection, {"owner": {"x": 1, "y": 0, "z": 2, "yaw": 0}})
        with mock.patch("bot_loker_wfh.office_state.supabase_configured", return_value=True), \
                mock.patch("bot_loker_wfh.office_state.supabase_request", return_value=[]):
            self.assertEqual(load_state_cloud(self.connection)["owner"]["x"], 1.0)

    def test_save_upserts_to_cloud_and_survives_outage(self):
        with mock.patch("bot_loker_wfh.office_state.supabase_configured", return_value=True), \
                mock.patch("bot_loker_wfh.office_state.supabase_request") as request:
            save_state(self.connection, {"staff": {"cora": {"x": 3, "y": 0, "z": 4}}})
        request.assert_called_once()
        self.assertEqual(request.call_args.kwargs["method"], "POST")
        self.assertEqual(request.call_args.kwargs["prefer"], "resolution=merge-duplicates")

        from bot_loker_wfh.database import SupabaseUnavailable
        with mock.patch("bot_loker_wfh.office_state.supabase_configured", return_value=True), \
                mock.patch("bot_loker_wfh.office_state.supabase_request", side_effect=SupabaseUnavailable("down")):
            self.assertEqual(save_state(self.connection, {"staff": {"cora": {"x": 5, "y": 0, "z": 6}}})["staff"]["cora"]["x"], 5.0)


if __name__ == "__main__":
    unittest.main()
