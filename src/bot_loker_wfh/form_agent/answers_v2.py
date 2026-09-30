"""Answers v2 model and loader supporting both v1 and v2 formats."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AnswerItem:
    key: str
    match: tuple[str, ...]
    type: str  # text | choice | number
    value: str


class AnswersStore:
    def __init__(self, items: list[AnswerItem]):
        self.items = items

    @classmethod
    def load(cls, path_or_content: str | Path | dict[str, Any]) -> "AnswersStore":
        if isinstance(path_or_content, dict):
            raw = path_or_content
        else:
            path = Path(path_or_content)
            if not path.is_file():
                return cls([])
            raw = json.loads(path.read_text(encoding="utf-8"))

        if not isinstance(raw, dict):
            return cls([])

        # Check version 2
        if raw.get("version") == 2 and isinstance(raw.get("answers"), list):
            items: list[AnswerItem] = []
            for ans in raw["answers"]:
                if not isinstance(ans, dict):
                    continue
                key = str(ans.get("key", "")).strip()
                match_list = ans.get("match", [])
                if isinstance(match_list, str):
                    match_list = [match_list]
                matches = tuple(str(m).strip().lower() for m in match_list if m)
                type_ = str(ans.get("type", "text")).strip().lower()
                val = str(ans.get("value", "")).strip()
                if key:
                    items.append(AnswerItem(key=key, match=matches, type=type_, value=val))
            return cls(items)

        # Legacy v1 format (dict of label -> value)
        items = []
        for key, val in raw.items():
            if str(key).strip():
                items.append(
                    AnswerItem(
                        key=str(key).strip(),
                        match=(str(key).strip().lower(),),
                        type="text",
                        value=str(val).strip(),
                    )
                )
        return cls(items)

    def get_available_keys(self) -> list[str]:
        return [f"answers.{item.key}" for item in self.items]

    def find_by_key(self, key: str) -> AnswerItem | None:
        clean_key = key.removeprefix("answers.")
        for item in self.items:
            if item.key == clean_key:
                return item
        return None

    def find_by_label(self, label: str) -> AnswerItem | None:
        lbl_lower = label.lower()
        for item in self.items:
            for m in item.match:
                if m in lbl_lower:
                    return item
        return None
