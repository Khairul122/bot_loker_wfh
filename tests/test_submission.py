import sqlite3
import unittest

from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.submission import (
    AmbiguousSubmissionError,
    SubmissionNotAllowedError,
    SubmissionOutcome,
    SubmissionService,
)


class SubmissionServiceTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)
        self.connection.execute(
            "INSERT INTO jobs (id, source, external_id, source_external_key, "
            "canonical_fingerprint, title, company, description, apply_url) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("job-1", "test", "1", "test:1", "fingerprint", "Engineer", "Acme", "Build APIs", "https://example.test/job"),
        )
        self.connection.execute(
            "INSERT INTO applications (id, job_id, idempotency_key, status, cover_letter, cv_summary) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("app-1", "job-1", "key-1", "APPROVED", "Cover", "Summary"),
        )
        self.connection.commit()

    def tearDown(self):
        self.connection.close()

    def test_success_claims_approved_and_stores_confirmation(self):
        service = SubmissionService(
            self.connection,
            submitter=lambda payload: SubmissionOutcome(
                "success", confirmation_url="https://example.test/confirmation", confirmation_reference="ref-1"
            ),
        )

        outcome = service.submit("app-1")

        self.assertEqual(outcome.result, "success")
        self.assertEqual(self._status(), "SUBMITTED")
        attempt = self.connection.execute(
            "SELECT attempt_number, result, confirmation_url, confirmation_reference "
            "FROM submission_attempts WHERE application_id = 'app-1'"
        ).fetchone()
        self.assertEqual(attempt, (1, "success", "https://example.test/confirmation", "ref-1"))

    def test_failed_and_timeout_are_recorded(self):
        for expected_result, expected_status, error in [
            ("failed", "SUBMIT_FAILED", RuntimeError("provider error")),
            ("timeout", "SUBMISSION_AMBIGUOUS", TimeoutError()),
        ]:
            self.connection.execute("UPDATE applications SET status = 'APPROVED' WHERE id = 'app-1'")
            self.connection.commit()
            service = SubmissionService(self.connection, submitter=lambda payload, error=error: (_ for _ in ()).throw(error))

            outcome = service.submit("app-1")

            self.assertEqual(outcome.result, expected_result)
            self.assertEqual(self._status(), expected_status)
            result = self.connection.execute(
                "SELECT result FROM submission_attempts WHERE application_id = 'app-1' "
                "ORDER BY attempt_number DESC LIMIT 1"
            ).fetchone()[0]
            self.assertEqual(result, expected_result)

    def test_ambiguous_exception_never_retries_automatically(self):
        calls = 0

        def submitter(payload):
            nonlocal calls
            calls += 1
            raise AmbiguousSubmissionError("after final click")

        service = SubmissionService(self.connection, submitter=submitter)
        first = service.submit("app-1")
        self.assertEqual(first.result, "ambiguous")
        self.assertEqual(self._status(), "SUBMISSION_AMBIGUOUS")
        with self.assertRaises(SubmissionNotAllowedError):
            service.submit("app-1")
        self.assertEqual(calls, 1)

    def test_only_approved_status_can_be_claimed(self):
        self.connection.execute("UPDATE applications SET status = 'PENDING_APPROVAL' WHERE id = 'app-1'")
        self.connection.commit()
        with self.assertRaises(SubmissionNotAllowedError):
            SubmissionService(self.connection, submitter=lambda payload: SubmissionOutcome("success")).submit("app-1")
        self.assertEqual(self._status(), "PENDING_APPROVAL")
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM submission_attempts").fetchone()[0], 0)

    def test_invalid_submitter_outcome_is_failed(self):
        outcome = SubmissionService(self.connection, submitter=lambda payload: "success").submit("app-1")
        self.assertEqual(outcome.result, "failed")
        self.assertEqual(self._status(), "SUBMIT_FAILED")

    def _status(self):
        return self.connection.execute("SELECT status FROM applications WHERE id = 'app-1'").fetchone()[0]


if __name__ == "__main__":
    unittest.main()
