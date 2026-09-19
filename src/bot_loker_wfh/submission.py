"""Guarded application submission orchestration."""

from __future__ import annotations

import logging
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from .logging_utils import StructuredLogger, sanitize_error


class SubmissionNotAllowedError(ValueError):
    """Raised when an application is not eligible for an automatic attempt."""


class AmbiguousSubmissionError(RuntimeError):
    """Raised when the final submit outcome cannot be verified."""


@dataclass(frozen=True)
class SubmissionOutcome:
    result: str
    confirmation_url: str | None = None
    confirmation_reference: str | None = None
    error_code: str | None = None


Submitter = Callable[[dict[str, Any]], SubmissionOutcome]


class SubmissionService:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        submitter: Submitter,
        logger: logging.Logger | None = None,
    ) -> None:
        self.connection = connection
        self.submitter = submitter
        self.logger = StructuredLogger(logger or logging.getLogger(__name__))

    def submit(self, application_id: str) -> SubmissionOutcome:
        application, attempt_number = self._claim(application_id)
        try:
            outcome = self.submitter(application)
            self._validate_outcome(outcome)
        except AmbiguousSubmissionError:
            outcome = SubmissionOutcome("ambiguous", error_code="ambiguous")
        except TimeoutError:
            outcome = SubmissionOutcome("timeout", error_code="timeout")
        except Exception as error:
            outcome = SubmissionOutcome("failed", error_code=sanitize_error(error))
        self._finish(application_id, attempt_number, outcome)
        return outcome

    def _claim(self, application_id: str) -> tuple[dict[str, Any], int]:
        self.connection.execute("BEGIN IMMEDIATE")
        row = self.connection.execute(
            "SELECT id, job_id, status, cover_letter, cv_summary, method "
            "FROM applications WHERE id = ?",
            (application_id,),
        ).fetchone()
        if row is None:
            self.connection.rollback()
            raise SubmissionNotAllowedError("application not found")
        if row[2] != "APPROVED":
            self.connection.rollback()
            raise SubmissionNotAllowedError(
                f"submission requires APPROVED status, got {row[2]}"
            )
        attempt_number = self.connection.execute(
            "SELECT COALESCE(MAX(attempt_number), 0) + 1 FROM submission_attempts "
            "WHERE application_id = ?",
            (application_id,),
        ).fetchone()[0]
        updated = self.connection.execute(
            "UPDATE applications SET status = 'SUBMITTING' "
            "WHERE id = ? AND status = 'APPROVED'",
            (application_id,),
        ).rowcount
        if updated != 1:
            self.connection.rollback()
            raise SubmissionNotAllowedError("application claim lost race")
        self._history(application_id, "APPROVED", "SUBMITTING")
        self.connection.execute(
            "INSERT INTO submission_attempts (id, application_id, attempt_number, result) "
            "VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), application_id, attempt_number, "started"),
        )
        self.connection.commit()
        return (
            {
                "id": row[0],
                "job_id": row[1],
                "cover_letter": row[3],
                "cv_summary": row[4],
                "method": row[5],
            },
            attempt_number,
        )

    def _finish(self, application_id: str, attempt_number: int, outcome: SubmissionOutcome) -> None:
        status_by_result = {
            "success": "SUBMITTED",
            "failed": "SUBMIT_FAILED",
            "timeout": "SUBMISSION_AMBIGUOUS",
            "ambiguous": "SUBMISSION_AMBIGUOUS",
        }
        if outcome.result not in status_by_result:
            raise ValueError(f"unsupported submission result: {outcome.result}")
        to_status = status_by_result[outcome.result]
        self.connection.execute("BEGIN IMMEDIATE")
        updated = self.connection.execute(
            "UPDATE applications SET status = ?, submitted_at = "
            "CASE WHEN ? = 'SUBMITTED' THEN strftime('%Y-%m-%dT%H:%M:%fZ', 'now') "
            "ELSE submitted_at END WHERE id = ? AND status = 'SUBMITTING'",
            (to_status, to_status, application_id),
        ).rowcount
        if updated != 1:
            self.connection.rollback()
            raise SubmissionNotAllowedError("submission state changed unexpectedly")
        self._history(application_id, "SUBMITTING", to_status)
        self.connection.execute(
            "UPDATE submission_attempts SET result = ?, error_message = ?, "
            "confirmation_url = ?, confirmation_reference = ? "
            "WHERE application_id = ? AND attempt_number = ?",
            (
                outcome.result,
                outcome.error_code,
                outcome.confirmation_url,
                outcome.confirmation_reference,
                application_id,
                attempt_number,
            ),
        )
        self.connection.commit()
        self.logger.event(
            "submission_complete", application_id=application_id, status=outcome.result
        )

    def _history(self, application_id: str, from_status: str, to_status: str) -> None:
        self.connection.execute(
            "INSERT INTO application_status_history "
            "(id, application_id, from_status, to_status, changed_by) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), application_id, from_status, to_status, "system"),
        )

    @staticmethod
    def _validate_outcome(outcome: SubmissionOutcome) -> None:
        if not isinstance(outcome, SubmissionOutcome):
            raise ValueError("submitter must return SubmissionOutcome")
