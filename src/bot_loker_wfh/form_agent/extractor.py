"""FormExtractor: Parses page snapshots into FormField list."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FormField:
    ref: str
    label: str
    role: str
    required: bool
    options: tuple[str, ...] = ()
    current_value: str = ""
    field_class: str = ""


class FormExtractor:
    """Parses BrowserMCP snapshot output (dict, list, or text string) into FormField list."""

    def extract(self, snapshot: Any) -> list[FormField]:
        fields: list[FormField] = []
        if isinstance(snapshot, dict):
            self._parse_node(snapshot, fields)
        elif isinstance(snapshot, list):
            for item in snapshot:
                if isinstance(item, dict):
                    self._parse_node(item, fields)
        elif isinstance(snapshot, str):
            self._parse_text(snapshot, fields)

        # Merge radio buttons with same group name if present
        return self._post_process(fields)

    def _parse_node(self, node: dict[str, Any], fields: list[FormField]) -> None:
        ref = str(node.get("ref") or node.get("id") or "")
        role = str(node.get("role") or "").lower()
        label = str(
            node.get("name") or node.get("label") or node.get("description") or ""
        ).strip()
        required = bool(node.get("required") or node.get("aria-required"))
        current_value = str(node.get("value") or "").strip()

        raw_opts = node.get("options") or node.get("choices") or []
        options = tuple(str(o).strip() for o in raw_opts if str(o).strip())

        interactive_roles = {
            "textbox",
            "combobox",
            "listbox",
            "checkbox",
            "radio",
            "button",
            "file",
            "input",
            "select",
            "textarea",
        }

        if ref and (role in interactive_roles or "input" in role or "button" in role):
            fields.append(
                FormField(
                    ref=ref,
                    label=label[:80],
                    role=role,
                    required=required,
                    options=options,
                    current_value=current_value,
                )
            )

        children = node.get("children") or node.get("nodes") or []
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    self._parse_node(child, fields)

    def _parse_text(self, text: str, fields: list[FormField]) -> None:
        # Simple regex parser for YAML/text format: e.g. "- ref: e12, role: textbox, label: Email..."
        lines = text.splitlines()
        for line in lines:
            line_str = line.strip()
            ref_match = re.search(r"ref[:=]\s*[\"']?([a-zA-Z0-9_-]+)[\"']?", line_str)
            if not ref_match:
                continue
            ref = ref_match.group(1)

            role_match = re.search(
                r"role[:=]\s*[\"']?([a-zA-Z0-9_-]+)[\"']?", line_str
            )
            role = role_match.group(1).lower() if role_match else "textbox"

            label_match = re.search(
                r"label[:=]\s*[\"']?([^,\"\']+)[\"']?", line_str
            ) or re.search(r"name[:=]\s*[\"']?([^,\"\']+)[\"']?", line_str)
            label = label_match.group(1).strip() if label_match else ""

            required = "required" in line_str.lower()
            val_match = re.search(r"value[:=]\s*[\"']?([^,\"\']+)[\"']?", line_str)
            current_value = val_match.group(1).strip() if val_match else ""

            opts_match = re.findall(r"options?[:=]\s*\[([^\]]+)\]", line_str)
            options: tuple[str, ...] = ()
            if opts_match:
                options = tuple(
                    s.strip().strip("'\"") for s in opts_match[0].split(",") if s.strip()
                )

            fields.append(
                FormField(
                    ref=ref,
                    label=label[:80],
                    role=role,
                    required=required,
                    options=options,
                    current_value=current_value,
                )
            )

    def _post_process(self, fields: list[FormField]) -> list[FormField]:
        # Filter duplicates by ref
        seen_refs: set[str] = set()
        unique_fields: list[FormField] = []
        for f in fields:
            if f.ref not in seen_refs:
                seen_refs.add(f.ref)
                unique_fields.append(f)
        return unique_fields
