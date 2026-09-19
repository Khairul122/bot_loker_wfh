"""Create reviewable application drafts from candidate jobs."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from .cover_letter import CoverLetterGenerator
from .cv_profile import SafeCvProfile
from .logging_utils import StructuredLogger, sanitize_error
from .skill_scorer import matched_skills
from .status_transitions import (
    InvalidTransitionError,
    TransitionActor,
    transition_application_status,
)


@dataclass(frozen=True)
class DraftResult:
    status: str  # created | existing | failed
    application_id: str | None = None
    application_status: str | None = None
    error_code: str | None = None


def template_cover_letter(
    *, title: str, company: str, description: str, profile: SafeCvProfile
) -> str:
    """Deterministic draft that only restates facts present in the profile."""
    matches = matched_skills(f"{title}\n{description}", profile.skills)
    if matches:
        stack = (
            f"Your posting mentions {_join(matches)}, which is part of the stack "
            "I work with regularly."
        )
    else:
        stack = f"My core stack includes {_join(list(profile.skills[:4]))}."
    paragraphs = [
        f"Dear Hiring Team at {company},",
        f"I am applying for the {title} position. {stack}",
    ]
    if profile.experience:
        paragraphs.append(profile.experience[0])
    if profile.projects:
        paragraphs.append("Recent work: " + "; ".join(profile.projects[:2]) + ".")
    paragraphs.append(
        "I would welcome the chance to discuss how I can contribute to your team."
    )
    paragraphs.append("Best regards")
    return "\n\n".join(paragraphs)


class DraftService:
    def __init__(
        self,
        connection: sqlite3.Connection,
        profile: SafeCvProfile,
        *,
        llm: Callable[[str], str] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.connection = connection
        self.profile = profile
        self.llm = llm
        self.logger = StructuredLogger(logger or logging.getLogger(__name__))

    def prepare(self, job_id: str) -> DraftResult:
        job = self.connection.execute(
            "SELECT title, company, description, status FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if job is None:
            return DraftResult("failed", error_code="job_not_found")
        title, company, description, job_status = job

        existing = self._application(job_id)
        if existing is not None:
            return DraftResult("existing", existing[0], existing[1])
        if job_status != "CANDIDATE":
            return DraftResult("failed", error_code="job_not_candidate")

        method = {"value": "template"}

        def provider(prompt: str) -> str:
            if self.llm is not None:
                try:
                    letter = str(self.llm(prompt) or "").strip()
                    if letter:
                        method["value"] = "llm"
                        return letter
                except Exception as error:
                    self.logger.warning(
                        "llm_fallback_to_template",
                        job_id=job_id,
                        error_code=sanitize_error(error),
                    )
            return template_cover_letter(
                title=title,
                company=company,
                description=description,
                profile=self.profile,
            )

        result = CoverLetterGenerator(
            self.connection, provider=provider
        ).generate_and_store(job_id=job_id, profile=self.profile)
        if result.application_id is None:
            return DraftResult("failed", error_code=result.error_code)
        if result.status == "created":
            self.connection.execute(
                "UPDATE applications SET method = ? WHERE id = ?",
                (method["value"], result.application_id),
            )
            self.connection.commit()

        current = self._application(job_id)
        if current is not None and current[1] == "DRAFT_READY":
            try:
                transition_application_status(
                    self.connection,
                    application_id=result.application_id,
                    to_status="PENDING_APPROVAL",
                    actor=TransitionActor.SYSTEM,
                )
            except InvalidTransitionError:
                return DraftResult("failed", error_code="transition_failed")
        final = self._application(job_id)
        return DraftResult(
            result.status, result.application_id, final[1] if final else None
        )

    def _application(self, job_id: str) -> tuple[str, str] | None:
        row = self.connection.execute(
            "SELECT id, status FROM applications WHERE job_id = ?", (job_id,)
        ).fetchone()
        return (str(row[0]), str(row[1])) if row else None


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]
