import sqlite3
import unittest

from bot_loker_wfh.employee_memory import MAX_RECORDS_PER_EMPLOYEE, ensure_schema as ensure_memory_schema, list_memories, remember
from bot_loker_wfh.meeting_runtime import add_event, create_meeting, ensure_schema as ensure_meeting_schema, set_status


class EmployeeMemoryTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        ensure_memory_schema(self.db)

    def tearDown(self):
        self.db.close()

    def test_valid_record_and_validation(self):
        record = remember(self.db, "sari", "Prefer concise CV evidence", kind="preference", metadata={"field": "cv"})
        self.assertEqual(record["metadata"], {"field": "cv"})
        self.assertEqual(list_memories(self.db, "sari")[0]["content"], "Prefer concise CV evidence")
        with self.assertRaises(ValueError):
            remember(self.db, "bad id", "x")
        with self.assertRaises(ValueError):
            remember(self.db, "sari", "x", importance=2)

    def test_memory_is_bounded(self):
        for index in range(MAX_RECORDS_PER_EMPLOYEE + 5):
            remember(self.db, "sari", f"record {index}", importance=0.1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM employee_memory").fetchone()[0], MAX_RECORDS_PER_EMPLOYEE)


class MeetingRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        ensure_meeting_schema(self.db)

    def tearDown(self):
        self.db.close()

    def test_lifecycle_and_events(self):
        meeting = create_meeting(self.db, "Daily review", "2026-10-11T09:00:00+07:00", ["sari", "cora"])
        self.assertEqual(meeting["starts_at"], "2026-10-11T02:00:00Z")
        set_status(self.db, meeting["id"], "active")
        event = add_event(self.db, meeting["id"], "sari", "decision", "Keep remote-only filter")
        self.assertEqual(event["event_type"], "decision")
        self.assertEqual(set_status(self.db, meeting["id"], "completed")["status"], "completed")

    def test_rejects_naive_time_and_duplicate_participants(self):
        with self.assertRaises(ValueError):
            create_meeting(self.db, "Review", "2026-10-11T09:00:00", [])
        with self.assertRaises(ValueError):
            create_meeting(self.db, "Review", "2026-10-11T09:00:00Z", ["sari", "sari"])


if __name__ == "__main__":
    unittest.main()
