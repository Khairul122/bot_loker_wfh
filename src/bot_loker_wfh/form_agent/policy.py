"""PolicyGuard: Validates fill actions against security and safety policies."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence

from bot_loker_wfh.form_agent.extractor import FormField

FORBIDDEN_CLICK_PATTERN = re.compile(
    r"\b(submit|apply|send|kirim|lamar|finish|complete|confirm|next|lanjut)\b",
    re.IGNORECASE,
)
EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_PATTERN = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")


@dataclass(frozen=True)
class PlanAction:
    ref: str
    action: str  # type | select | check | answer
    value: str = ""
    source: str = ""
    confidence: float = 1.0


@dataclass(frozen=True)
class RejectedAction:
    ref: str
    reason: str
    rule: str
    action: PlanAction


@dataclass(frozen=True)
class PolicyCheckResult:
    approved: list[PlanAction]
    rejected: list[RejectedAction]


class PolicyGuard:
    def __init__(
        self,
        *,
        min_confidence: float = 0.7,
        max_actions: int = 60,
        open_button_label: str | None = None,
    ):
        self.min_confidence = min_confidence
        self.max_actions = max_actions
        self.open_button_label = open_button_label

    def evaluate(
        self,
        actions: Sequence[PlanAction],
        fields: Sequence[FormField],
        available_keys: Sequence[str],
    ) -> PolicyCheckResult:
        field_map = {f.ref: f for f in fields}
        approved: list[PlanAction] = []
        rejected: list[RejectedAction] = []

        avail_set = set(available_keys)

        for idx, act in enumerate(actions):
            # PG-10: too_many_actions
            if len(approved) >= self.max_actions:
                rejected.append(
                    RejectedAction(
                        ref=act.ref,
                        reason="too_many_actions",
                        rule="PG-10",
                        action=act,
                    )
                )
                continue

            # PG-01: unknown_ref
            if act.ref not in field_map:
                rejected.append(
                    RejectedAction(
                        ref=act.ref,
                        reason="unknown_ref",
                        rule="PG-01",
                        action=act,
                    )
                )
                continue

            field = field_map[act.ref]
            f_class = field.field_class

            # PG-09: low_confidence
            if act.confidence < self.min_confidence:
                rejected.append(
                    RejectedAction(
                        ref=act.ref,
                        reason="low_confidence",
                        rule="PG-09",
                        action=act,
                    )
                )
                continue

            # PG-02: protected_field (captcha, upload, sensitive, legal)
            if f_class in {"captcha", "upload", "sensitive", "legal"}:
                rejected.append(
                    RejectedAction(
                        ref=act.ref,
                        reason="protected_field",
                        rule="PG-02",
                        action=act,
                    )
                )
                continue

            # PG-07: check on legal
            if act.action == "check" and f_class == "legal":
                rejected.append(
                    RejectedAction(
                        ref=act.ref,
                        reason="protected_field",
                        rule="PG-07",
                        action=act,
                    )
                )
                continue

            # PG-08: forbidden_click
            if (
                field.role == "button"
                or act.action == "check"
                or FORBIDDEN_CLICK_PATTERN.search(field.label)
            ):
                if FORBIDDEN_CLICK_PATTERN.search(field.label):
                    is_open_btn = False
                    if (
                        self.open_button_label
                        and self.open_button_label.lower() in field.label.lower()
                    ):
                        is_open_btn = True
                    if not is_open_btn:
                        rejected.append(
                            RejectedAction(
                                ref=act.ref,
                                reason="forbidden_click",
                                rule="PG-08",
                                action=act,
                            )
                        )
                        continue

            # PG-03: salary_needs_answer
            if f_class == "salary":
                if not (act.source and act.source.startswith("answers.")):
                    rejected.append(
                        RejectedAction(
                            ref=act.ref,
                            reason="salary_needs_answer",
                            rule="PG-03",
                            action=act,
                        )
                    )
                    continue

            # PG-04: identity_must_be_placeholder
            if f_class in {"identity", "link"}:
                val = act.value.strip()
                if not (val.startswith("{{applicant.") and val.endswith("}}")):
                    rejected.append(
                        RejectedAction(
                            ref=act.ref,
                            reason="identity_must_be_placeholder",
                            rule="PG-04",
                            action=act,
                        )
                    )
                    continue

            # PG-05: unknown_key
            val = act.value.strip()
            if val.startswith("{{") and val.endswith("}}"):
                key_name = val[2:-2].strip()
                if key_name not in avail_set:
                    rejected.append(
                        RejectedAction(
                            ref=act.ref,
                            reason="unknown_key",
                            rule="PG-05",
                            action=act,
                        )
                    )
                    continue

            # PG-06: invalid_option
            if act.action == "select":
                clean_val = act.value.strip()
                opt_matches = [
                    opt for opt in field.options if opt.lower() == clean_val.lower()
                ]
                if not opt_matches and not clean_val.startswith("{{"):
                    rejected.append(
                        RejectedAction(
                            ref=act.ref,
                            reason="invalid_option",
                            rule="PG-06",
                            action=act,
                        )
                    )
                    continue

            # PG-11: pii_in_free_text
            if f_class not in {"identity", "link"}:
                if EMAIL_PATTERN.search(act.value) or PHONE_PATTERN.search(act.value):
                    rejected.append(
                        RejectedAction(
                            ref=act.ref,
                            reason="pii_in_free_text",
                            rule="PG-11",
                            action=act,
                        )
                    )
                    continue

            approved.append(act)

        return PolicyCheckResult(approved=approved, rejected=rejected)
