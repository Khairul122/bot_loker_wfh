"""Safe, non-submitting browser form prototype for ATS applications."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlparse


class Locator(Protocol):
    def fill(self, value: str) -> None: ...
    def set_input_files(self, path: str) -> None: ...


class DryRunPage(Protocol):
    url: str
    def get_by_label(self, label: str, *, exact: bool = False) -> Locator: ...


@dataclass(frozen=True)
class TargetForm:
    ats: str
    slug: str
    allowed_host: str
    allowed_path_prefix: str

    def allows(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme == "https" and parsed.netloc == self.allowed_host and parsed.path.startswith(self.allowed_path_prefix)


@dataclass(frozen=True)
class ApplicationFormData:
    first_name: str
    last_name: str
    email: str
    phone: str
    resume_path: str
    cover_letter: str
    custom_answers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DryRunResult:
    status: str
    filled_fields: tuple[str, ...] = ()
    fallback_reason: str | None = None


DEFAULT_FIELD_MAPPING = {
    "first_name": "First Name",
    "last_name": "Last Name",
    "email": "Email",
    "phone": "Phone",
    "resume_path": "Resume",
    "cover_letter": "Cover Letter",
}


class ManualFallbackError(RuntimeError):
    """Raised internally when a dry-run cannot safely continue."""


class DryRunFormFiller:
    def __init__(self, *, field_mapping: dict[str, str] | None = None) -> None:
        self.field_mapping = dict(field_mapping or DEFAULT_FIELD_MAPPING)

    def fill(
        self,
        page: DryRunPage,
        *,
        target: TargetForm,
        data: ApplicationFormData,
        required_custom_questions: tuple[str, ...] = (),
    ) -> DryRunResult:
        filled: list[str] = []
        try:
            if target.ats not in {"greenhouse", "lever"}:
                raise ManualFallbackError("unsupported ATS")
            if not target.allows(page.url):
                raise ManualFallbackError("target URL is not allowlisted")
            missing_questions = [
                label for label in required_custom_questions
                if label not in data.custom_answers
            ]
            if missing_questions:
                raise ManualFallbackError(
                    "required custom question needs manual answer"
                )
            self._fill_text(page, "first_name", data.first_name, filled)
            self._fill_text(page, "last_name", data.last_name, filled)
            self._fill_text(page, "email", data.email, filled)
            self._fill_text(page, "phone", data.phone, filled)
            self._upload(page, "resume_path", data.resume_path, filled)
            self._fill_text(page, "cover_letter", data.cover_letter, filled)
            for label, answer in data.custom_answers.items():
                self._fill_label(page, label, answer, filled)
            return DryRunResult("ready_without_submit", tuple(filled))
        except Exception as error:
            return DryRunResult("manual_fallback", tuple(filled), str(error))

    def _fill_text(
        self, page: DryRunPage, field: str, value: str, filled: list[str]
    ) -> None:
        if not value.strip():
            raise ManualFallbackError(f"empty required field: {field}")
        self._fill_label(page, self.field_mapping[field], value, filled)

    def _upload(
        self, page: DryRunPage, field: str, path: str, filled: list[str]
    ) -> None:
        if not path.strip():
            raise ManualFallbackError("resume path is empty")
        page.get_by_label(self.field_mapping[field], exact=False).set_input_files(path)
        filled.append(field)

    def _fill_label(
        self, page: DryRunPage, label: str, value: str, filled: list[str]
    ) -> None:
        page.get_by_label(label, exact=False).fill(value)
        filled.append(label)
