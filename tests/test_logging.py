import io
import json
import logging
import unittest

from bot_loker_wfh.logging_utils import StructuredLogger, sanitize_error


class StructuredLoggingTest(unittest.TestCase):
    def setUp(self):
        self.stream = io.StringIO()
        self.logger = logging.getLogger("structured-test")
        self.logger.handlers.clear()
        self.logger.propagate = False
        handler = logging.StreamHandler(self.stream)
        handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    def test_log_is_json_with_allowlisted_metadata(self):
        StructuredLogger(self.logger, run_id="run-1").event(
            "fetch_complete",
            run_id="ignored-run",
            job_id="job-1",
            application_id="app-1",
            source="remoteok",
            status="success",
            duration_ms=42,
            error_code=None,
            description="PRIVATE JOB DESCRIPTION",
            cover_letter="PRIVATE COVER LETTER",
            token="secret-token",
        )

        record = json.loads(self.stream.getvalue())
        self.assertEqual(record["event"], "fetch_complete")
        self.assertEqual(record["run_id"], "run-1")
        self.assertEqual(record["job_id"], "job-1")
        self.assertEqual(record["duration_ms"], 42)
        self.assertNotIn("description", record)
        self.assertNotIn("cover_letter", record)
        self.assertNotIn("token", record)

    def test_sensitive_values_are_redacted_even_in_error_context(self):
        StructuredLogger(self.logger).error(
            "fetch_failed",
            run_id="run-2",
            source="remotive",
            error_code="network_timeout",
            error=ValueError("phone 08123456789 address Jalan Rahasia"),
        )

        output = self.stream.getvalue()
        record = json.loads(output)
        self.assertEqual(record["error_code"], "network_timeout")
        self.assertNotIn("08123456789", output)
        self.assertNotIn("Jalan Rahasia", output)
        self.assertNotIn("error", record)

    def test_sanitize_error_returns_stable_code_without_message(self):
        result = sanitize_error(TimeoutError("secret provider response"))

        self.assertEqual(result, "timeout")
        self.assertNotIn("secret", result)


if __name__ == "__main__":
    unittest.main()
