import sqlite3
import unittest

from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.status_transitions import (
    InvalidTransitionError,
    TransitionActor,
    transition_application_status,
    transition_job_status,
)


class StatusTransitionTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_schema(self.connection)
        self.connection.execute(
            "INSERT INTO jobs (id, source, external_id, source_external_key, "
            "canonical_fingerprint, title, company, description, apply_url) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "job-1",
                "remoteok",
                "123",
                "remoteok:123",
                "canonical-123",
                "Backend Developer",
                "Acme",
                "Description",
                "https://example.com/jobs/123",
            ),
        )
        self.connection.execute(
            "INSERT INTO applications (id, job_id, idempotency_key, cover_letter, "
            "cv_summary, method) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "application-1",
                "job-1",
                "application-key-1",
                "Cover letter",
                "CV summary",
                "manual",
            ),
        )
        self.connection.commit()

    def tearDown(self):
        self.connection.close()

    def test_valid_job_transition_updates_status_without_application_history(self):
        transition_job_status(
            self.connection,
            job_id="job-1",
            to_status="CANDIDATE",
            actor=TransitionActor.SYSTEM,
        )

        job_status = self.connection.execute(
            "SELECT status FROM jobs WHERE id = ?", ("job-1",)
        ).fetchone()[0]
        history_count = self.connection.execute(
            "SELECT COUNT(*) FROM application_status_history"
        ).fetchone()[0]

        self.assertEqual(job_status, "CANDIDATE")
        self.assertEqual(history_count, 0)

    def test_valid_application_transition_updates_status_and_writes_history(self):
        transition_application_status(
            self.connection,
            application_id="application-1",
            to_status="PENDING_APPROVAL",
            actor=TransitionActor.SYSTEM,
        )

        application_status = self.connection.execute(
            "SELECT status FROM applications WHERE id = ?", ("application-1",)
        ).fetchone()[0]
        history = self.connection.execute(
            "SELECT from_status, to_status, changed_by "
            "FROM application_status_history WHERE application_id = ?",
            ("application-1",),
        ).fetchone()

        self.assertEqual(application_status, "PENDING_APPROVAL")
        self.assertEqual(history, ("DRAFT_READY", "PENDING_APPROVAL", "system"))

    def test_invalid_transition_is_rejected_with_clear_error(self):
        with self.assertRaisesRegex(
            InvalidTransitionError,
            "Invalid application transition: DRAFT_READY -> SUBMITTED",
        ):
            transition_application_status(
                self.connection,
                application_id="application-1",
                to_status="SUBMITTED",
                actor=TransitionActor.SYSTEM,
            )

    def test_terminal_state_rejects_normal_transition(self):
        transition_application_status(
            self.connection,
            application_id="application-1",
            to_status="PENDING_APPROVAL",
            actor=TransitionActor.SYSTEM,
        )
        transition_application_status(
            self.connection,
            application_id="application-1",
            to_status="REJECTED_BY_USER",
            actor=TransitionActor.USER,
        )

        with self.assertRaisesRegex(
            InvalidTransitionError,
            "Invalid application transition: REJECTED_BY_USER -> APPROVED",
        ):
            transition_application_status(
                self.connection,
                application_id="application-1",
                to_status="APPROVED",
                actor=TransitionActor.USER,
            )

    def test_manual_correction_policy_requires_explicit_reason(self):
        transition_application_status(
            self.connection,
            application_id="application-1",
            to_status="PENDING_APPROVAL",
            actor=TransitionActor.SYSTEM,
        )
        transition_application_status(
            self.connection,
            application_id="application-1",
            to_status="REJECTED_BY_USER",
            actor=TransitionActor.USER,
        )

        with self.assertRaisesRegex(InvalidTransitionError, "requires a reason"):
            transition_application_status(
                self.connection,
                application_id="application-1",
                to_status="PENDING_APPROVAL",
                actor=TransitionActor.USER,
                manual_correction=True,
            )

        transition_application_status(
            self.connection,
            application_id="application-1",
            to_status="PENDING_APPROVAL",
            actor=TransitionActor.USER,
            manual_correction=True,
            reason="Wrong button pressed",
        )
        status = self.connection.execute(
            "SELECT status FROM applications WHERE id = ?", ("application-1",)
        ).fetchone()[0]
        history_count = self.connection.execute(
            "SELECT COUNT(*) FROM application_status_history WHERE application_id = ?",
            ("application-1",),
        ).fetchone()[0]

        self.assertEqual(status, "PENDING_APPROVAL")
        self.assertEqual(history_count, 3)


if __name__ == "__main__":
    unittest.main()
