"""Editable, privacy-safe CV profile for LLM prompts."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path
from typing import Iterable


_SENSITIVE_PATTERNS = (
    re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b", re.IGNORECASE),
    re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)"),
    re.compile(r"\b(?:date of birth|dob|birth date|tanggal lahir)\s*[:=-]?\s*[^\n;]+", re.IGNORECASE),
    re.compile(r"\b(?:home address|address|alamat|street|jalan)\s*[:=-]?\s*[^\n;]+", re.IGNORECASE),
    re.compile(r"\b(?:national id|nik|passport|ssn|ktp)\s*[:#-]?\s*[A-Z0-9-]{5,}\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class SafeCvProfile:
    skills: tuple[str, ...] = ()
    experience: tuple[str, ...] = ()
    projects: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("skills", "experience", "projects"):
            values = getattr(self, field_name)
            cleaned = tuple(_sanitize_text(value) for value in values)
            cleaned = tuple(value for value in cleaned if value)
            object.__setattr__(self, field_name, cleaned)

    @classmethod
    def from_values(
        cls,
        *,
        skills: Iterable[str] = (),
        experience: Iterable[str] = (),
        projects: Iterable[str] = (),
    ) -> "SafeCvProfile":
        return cls(tuple(skills), tuple(experience), tuple(projects))

    def to_summary(self) -> str:
        sections = []
        if self.skills:
            sections.append("Skills: " + ", ".join(self.skills))
        if self.experience:
            sections.append("Experience: " + "; ".join(self.experience))
        if self.projects:
            sections.append("Projects: " + "; ".join(self.projects))
        return "\n".join(sections)

    def edited(
        self,
        *,
        skills: Iterable[str] | None = None,
        experience: Iterable[str] | None = None,
        projects: Iterable[str] | None = None,
    ) -> "SafeCvProfile":
        return SafeCvProfile(
            skills=self.skills if skills is None else tuple(skills),
            experience=self.experience if experience is None else tuple(experience),
            projects=self.projects if projects is None else tuple(projects),
        )


def _sanitize_text(value: object) -> str:
    sanitized = " ".join(str(value or "").split()).strip()
    for pattern in _SENSITIVE_PATTERNS:
        sanitized = pattern.sub("[redacted]", sanitized)
    return sanitized


def load_profile(path: str | Path) -> SafeCvProfile:
    """Load a sanitized profile from a JSON file with skills/experience/projects."""
    profile_path = Path(path)
    if not profile_path.is_file():
        raise FileNotFoundError(
            f"Profile file not found: {profile_path}. "
            "Copy resume/profile.example.json to that path and edit it."
        )
    data = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    return SafeCvProfile.from_values(
        skills=data.get("skills", ()),
        experience=data.get("experience", ()),
        projects=data.get("projects", ()),
    )
