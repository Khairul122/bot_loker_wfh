"""FieldClassifier: Rule-based field classification without AI."""

from __future__ import annotations

from typing import Sequence

from bot_loker_wfh.form_agent.answers_v2 import AnswersStore
from bot_loker_wfh.form_agent.extractor import FormField

CAPTCHA_KEYWORDS = (
    "captcha",
    "hcaptcha",
    "recaptcha",
    "turnstile",
    "i am human",
    "not a robot",
)
UPLOAD_KEYWORDS = ("resume", "cv", "attach", "upload")
SENSITIVE_KEYWORDS = (
    "gender",
    "sex",
    "race",
    "ethnicity",
    "veteran",
    "disability",
    "pronoun",
    "sexual orientation",
    "religion",
    "agama",
    "suku",
    "date of birth",
    "tanggal lahir",
)
LEGAL_KEYWORDS = (
    "consent",
    "agree",
    "certify",
    "acknowledge",
    "privacy",
    "gdpr",
    "terms",
    "data processing",
    "persetujuan",
    "syarat",
)
SALARY_KEYWORDS = ("salary", "compensation", "gaji", "expected pay", "rate")
IDENTITY_KEYWORDS = (
    "first name",
    "last name",
    "full name",
    "name",
    "email",
    "phone",
    "nama",
    "telepon",
)
LINK_KEYWORDS = ("linkedin", "github", "portfolio", "website", "url")
COVER_LETTER_KEYWORDS = (
    "cover letter",
    "additional information",
    "anything else",
    "motivation letter",
    "proposal",  # freelance bid forms: "Describe your proposal" / "Jelaskan proposal Anda"
)


class FieldClassifier:
    def __init__(self, answers_store: AnswersStore | None = None):
        self.answers_store = answers_store or AnswersStore([])

    def classify(self, field: FormField) -> str:
        lbl_lower = field.label.lower()

        # 1. captcha
        if any(k in lbl_lower for k in CAPTCHA_KEYWORDS):
            return "captcha"

        # 2. upload
        if field.role == "file" or any(k in lbl_lower for k in UPLOAD_KEYWORDS):
            return "upload"

        # 3. sensitive
        if any(k in lbl_lower for k in SENSITIVE_KEYWORDS):
            return "sensitive"

        # 4. legal
        if any(k in lbl_lower for k in LEGAL_KEYWORDS):
            return "legal"

        # 5. salary
        if any(k in lbl_lower for k in SALARY_KEYWORDS):
            return "salary"

        # 6. identity
        if any(k in lbl_lower for k in IDENTITY_KEYWORDS):
            return "identity"

        # 7. link
        if any(k in lbl_lower for k in LINK_KEYWORDS):
            return "link"

        # 8. cover_letter
        if any(k in lbl_lower for k in COVER_LETTER_KEYWORDS):
            return "cover_letter"

        # 9. known_answer
        if self.answers_store.find_by_label(field.label):
            return "known_answer"

        # 10. open_question
        if (field.role in {"textbox", "textarea", "input"} or not field.role) and (
            len(field.label) > 25 or field.label.strip().endswith("?")
        ):
            return "open_question"

        # 11. choice
        if field.role in {"combobox", "listbox", "radio", "checkbox", "select"}:
            return "choice"

        # 12. unknown
        return "unknown"

    def classify_all(self, fields: Sequence[FormField]) -> list[FormField]:
        result: list[FormField] = []
        for f in fields:
            cls_name = self.classify(f)
            result.append(
                FormField(
                    ref=f.ref,
                    label=f.label,
                    role=f.role,
                    required=f.required,
                    options=f.options,
                    current_value=f.current_value,
                    field_class=cls_name,
                )
            )
        return result
