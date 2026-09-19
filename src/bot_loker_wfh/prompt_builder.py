"""Prompt construction constrained to job text and safe CV summary."""

from __future__ import annotations

from .cv_profile import SafeCvProfile


def build_cover_letter_prompt(job_description: str, profile: SafeCvProfile) -> str:
    description = " ".join(str(job_description or "").split()).strip()
    summary = profile.to_summary().strip()
    if not description:
        raise ValueError("job_description is required")
    if not summary:
        raise ValueError("safe CV profile is empty")
    return (
        "Write a concise, truthful cover letter for the job description below. "
        "Mention relevant technologies and responsibilities from the description. "
        "Use only evidence from the candidate summary, do not invent experience, "
        "and do not include placeholders or personal contact details.\n\n"
        f"JOB DESCRIPTION:\n{description}\n\n"
        f"CANDIDATE SUMMARY:\n{summary}"
    )
