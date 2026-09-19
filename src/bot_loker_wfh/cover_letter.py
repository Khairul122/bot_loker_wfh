"""LLM cover-letter generation with privacy-safe logging and persistence."""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .cv_profile import SafeCvProfile
from .logging_utils import StructuredLogger, sanitize_error
from .prompt_builder import build_cover_letter_prompt


@dataclass(frozen=True)
class GenerationResult:
    status: str
    application_id: str | None = None
    error_code: str | None = None


class CoverLetterGenerator:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        provider: Callable[[str], str],
        logger: logging.Logger | None = None,
    ) -> None:
        self.connection = connection
        self.provider = provider
        self.logger = StructuredLogger(logger or logging.getLogger(__name__))

    def generate_and_store(
        self, *, job_id: str, profile: SafeCvProfile
    ) -> GenerationResult:
        existing = self._existing_application(job_id)
        if existing is not None:
            return GenerationResult("existing", application_id=existing)

        job = self.connection.execute(
            "SELECT description FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if job is None:
            return GenerationResult("failed", error_code="job_not_found")

        try:
            prompt = build_cover_letter_prompt(job[0], profile)
            cover_letter = str(self.provider(prompt) or "").strip()
            if not cover_letter:
                raise ValueError("provider returned empty cover letter")
        except Exception as error:
            error_code = sanitize_error(error)
            self.logger.error(
                "llm_generation_failed", job_id=job_id, error_code=error_code
            )
            return GenerationResult("failed", error_code=error_code)

        application_id = str(uuid.uuid4())
        idempotency_key = hashlib.sha256(
            f"{job_id}:llm:{profile.to_summary()}".encode("utf-8")
        ).hexdigest()
        try:
            self.connection.execute(
                "INSERT INTO applications (id, job_id, idempotency_key, status, "
                "cover_letter, cv_summary, method) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    application_id,
                    job_id,
                    idempotency_key,
                    "DRAFT_READY",
                    cover_letter,
                    profile.to_summary(),
                    "llm",
                ),
            )
            self.connection.commit()
        except sqlite3.IntegrityError:
            self.connection.rollback()
            existing = self._existing_application(job_id)
            if existing is not None:
                return GenerationResult("existing", application_id=existing)
            self.logger.error(
                "llm_persistence_failed", job_id=job_id, error_code="database_error"
            )
            return GenerationResult("failed", error_code="database_error")

        self.logger.event(
            "llm_generation_complete",
            job_id=job_id,
            application_id=application_id,
            status="success",
        )
        return GenerationResult("created", application_id=application_id)

    def _existing_application(self, job_id: str) -> str | None:
        row = self.connection.execute(
            "SELECT id FROM applications WHERE job_id = ?", (job_id,)
        ).fetchone()
        return str(row[0]) if row else None
