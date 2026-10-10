"""ValueResolver and Executor for FormAgent."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from bot_loker_wfh.form_agent.answers_v2 import AnswersStore
from bot_loker_wfh.form_agent.extractor import FormExtractor, FormField
from bot_loker_wfh.form_agent.policy import PlanAction


@dataclass(frozen=True)
class ExecutionEvent:
    ref: str
    label: str
    role: str
    field_class: str
    action: str  # filled | ai_answered | verify_failed | error
    source: str
    value_used: str = ""
    reason: str = ""
    confidence: float = 1.0


class ValueResolver:
    def __init__(
        self,
        applicant_data: dict[str, Any] | None = None,
        answers_store: AnswersStore | None = None,
        cover_letter: str = "",
        bid_data: dict[str, str] | None = None,
    ):
        self.applicant_data = applicant_data or {}
        self.answers_store = answers_store or AnswersStore([])
        self.cover_letter = cover_letter
        self.bid_data = bid_data or {}

    @classmethod
    def from_files(
        cls,
        applicant_path: str | Path,
        answers_path: str | Path,
        cover_letter: str = "",
    ) -> "ValueResolver":
        app_dict: dict[str, Any] = {}
        app_file = Path(applicant_path)
        if app_file.is_file():
            try:
                app_dict = json.loads(app_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        store = AnswersStore.load(answers_path)
        return cls(
            applicant_data=app_dict, answers_store=store, cover_letter=cover_letter
        )

    def get_available_keys(self) -> list[str]:
        keys = [
            "applicant.first_name",
            "applicant.last_name",
            "applicant.full_name",
            "applicant.email",
            "applicant.phone",
            "applicant.linkedin",
            "applicant.github",
            "applicant.website",
            "application.cover_letter",
        ]
        keys.extend(self.answers_store.get_available_keys())
        keys.extend(self.bid_data)
        return keys

    def resolve(self, placeholder_or_val: str) -> str | None:
        val = placeholder_or_val.strip()
        if not (val.startswith("{{") and val.endswith("}}")):
            return val

        key = val[2:-2].strip()

        if key.startswith("applicant."):
            prop = key.removeprefix("applicant.")
            res = self.applicant_data.get(prop)
            if res is not None and str(res).strip():
                return str(res).strip()
            return None

        if key.startswith("bid."):
            value = self.bid_data.get(key)
            return value.strip() if value and value.strip() else None

        if key == "application.cover_letter":
            if self.cover_letter.strip():
                return self.cover_letter.strip()
            return None

        if key.startswith("answers."):
            item = self.answers_store.find_by_key(key)
            if item and item.value.strip():
                return item.value.strip()
            return None

        return None


class Executor:
    def __init__(self, browser_client: Any, value_resolver: ValueResolver):
        self.client = browser_client
        self.resolver = value_resolver

    def execute_plan(
        self,
        actions: Sequence[PlanAction],
        fields: Sequence[FormField],
    ) -> list[ExecutionEvent]:
        field_map = {f.ref: f for f in fields}
        events: list[ExecutionEvent] = []

        for act in actions:
            field = field_map.get(act.ref)
            if not field:
                events.append(
                    ExecutionEvent(
                        ref=act.ref,
                        label="",
                        role="",
                        field_class="",
                        action="error",
                        source=act.source,
                        reason="field_not_found",
                        confidence=act.confidence,
                    )
                )
                continue

            resolved_val = self.resolver.resolve(act.value)
            if resolved_val is None:
                events.append(
                    ExecutionEvent(
                        ref=act.ref,
                        label=field.label,
                        role=field.role,
                        field_class=field.field_class,
                        action="error",
                        source=act.source,
                        reason="value_resolution_failed",
                        confidence=act.confidence,
                    )
                )
                continue

            time.sleep(0.3)  # 300 ms pacing between actions

            element_name = field.label or field.role or "field"

            try:
                if act.action in {"type", "answer"}:
                    self.client.call_tool(
                        "browser_type",
                        {
                            "element": element_name,
                            "ref": act.ref,
                            "text": resolved_val,
                            "submit": False,
                        },
                    )
                    act_type = "ai_answered" if act.action == "answer" else "filled"
                    events.append(
                        ExecutionEvent(
                            ref=act.ref,
                            label=field.label,
                            role=field.role,
                            field_class=field.field_class,
                            action=act_type,
                            source=act.source,
                            value_used=resolved_val,
                            confidence=act.confidence,
                        )
                    )
                elif act.action == "select":
                    self.client.call_tool(
                        "browser_select_option",
                        {
                            "element": element_name,
                            "ref": act.ref,
                            "values": [resolved_val],
                        },
                    )
                    events.append(
                        ExecutionEvent(
                            ref=act.ref,
                            label=field.label,
                            role=field.role,
                            field_class=field.field_class,
                            action="filled",
                            source=act.source,
                            value_used=resolved_val,
                            confidence=act.confidence,
                        )
                    )
                elif act.action == "check":
                    self.client.call_tool(
                        "browser_click",
                        {"element": element_name, "ref": act.ref},
                    )
                    events.append(
                        ExecutionEvent(
                            ref=act.ref,
                            label=field.label,
                            role=field.role,
                            field_class=field.field_class,
                            action="filled",
                            source=act.source,
                            value_used="checked",
                            confidence=act.confidence,
                        )
                    )
            except Exception as err:
                events.append(
                    ExecutionEvent(
                        ref=act.ref,
                        label=field.label,
                        role=field.role,
                        field_class=field.field_class,
                        action="failed",
                        source=act.source,
                        reason=str(err),
                        confidence=act.confidence,
                    )
                )

        return events
