"""FormExtractor: Parses page snapshots into FormField list."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


INTERACTIVE_ROLES = frozenset({
    "textbox", "combobox", "listbox", "checkbox", "radio", "button", "file",
    "input", "select", "textarea", "spinbutton",
})


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
        page_url: str = ""

        text_content = ""
        if isinstance(snapshot, dict):
            if "content" in snapshot and isinstance(snapshot["content"], list):
                text_content = "\n".join(
                    str(item.get("text", ""))
                    for item in snapshot["content"]
                    if isinstance(item, dict) and "text" in item
                )
            elif "children" in snapshot or "nodes" in snapshot:
                self._parse_dict_nodes(snapshot, fields)
                return self._post_process(fields)
            else:
                text_content = str(snapshot)
        elif isinstance(snapshot, list):
            for item in snapshot:
                if isinstance(item, dict) and ("children" in item or "nodes" in item):
                    self._parse_dict_nodes(item, fields)
                else:
                    text_content += "\n" + str(item)
            if fields:
                return self._post_process(fields)
        elif isinstance(snapshot, str):
            text_content = snapshot

        if text_content:
            page_url, parsed_fields = self._parse_browsermcp_text(text_content)
            fields.extend(parsed_fields)

        return self._post_process(fields)

    def _parse_browsermcp_text(self, text: str) -> tuple[str, list[FormField]]:
        page_url = ""
        fields: list[FormField] = []

        url_match = re.search(r"Page URL:\s*(\S+)", text)
        if url_match:
            page_url = url_match.group(1)

        yaml_block_match = re.search(
            r"```yaml\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE
        )
        target_text = yaml_block_match.group(1) if yaml_block_match else text

        lines = target_text.splitlines()
        parent_field_options: list[str] = []
        parent_field_index: int | None = None

        line_pattern = re.compile(
            r"^\s*-\s+([a-zA-Z0-9_-]+)\s+[\"']([^\"']+)[\"']\s*(.*)$"
        )
        ref_pattern = re.compile(r"\[ref=([a-zA-Z0-9_-]+)\]")

        for line in lines:
            line_str = line.rstrip()
            if not line_str.strip():
                continue

            match = line_pattern.match(line_str)
            # Unlabeled aria node ("- generic [ref=e9]"): a field only if its role is interactive
            aria = re.match(r"^\s*-\s+([a-zA-Z]+)\s*\[", line_str)
            if not match and aria and aria.group(1).lower() not in INTERACTIVE_ROLES:
                continue
            if not match:
                # Check legacy or key-value ref format
                ref_m = ref_pattern.search(line_str) or re.search(
                    r"ref[:=]\s*[\"']?([a-zA-Z0-9_-]+)[\"']?", line_str
                )
                if ref_m:
                    ref = ref_m.group(1)
                    role_m = re.search(
                        r"role[:=]\s*[\"']?([a-zA-Z0-9_-]+)[\"']?", line_str
                    )
                    role = role_m.group(1).lower() if role_m else (
                        aria.group(1).lower() if aria else "textbox"
                    )
                    lbl_m = re.search(
                        r"label[:=]\s*[\"']?([^,\"\']+)[\"']?", line_str
                    ) or re.search(r"name[:=]\s*[\"']?([^,\"\']+)[\"']?", line_str)
                    label = lbl_m.group(1).strip() if lbl_m else ""
                    is_req = "required" in line_str.lower()
                    fields.append(
                        FormField(
                            ref=ref,
                            label=label[:80],
                            role=role,
                            required=is_req,
                        )
                    )
                continue

            role = match.group(1).lower()
            raw_label = match.group(2).strip()
            rest = match.group(3).strip()

            ref_m = ref_pattern.search(rest)
            ref = ref_m.group(1) if ref_m else ""

            # Check if option under combobox / listbox / select
            if role in {"option", "choice"} and parent_field_index is not None:
                option_val = raw_label.removesuffix("*").strip()
                curr_parent = fields[parent_field_index]
                new_opts = curr_parent.options + (option_val,)
                fields[parent_field_index] = FormField(
                    ref=curr_parent.ref,
                    label=curr_parent.label,
                    role=curr_parent.role,
                    required=curr_parent.required,
                    options=new_opts,
                    current_value=curr_parent.current_value,
                )
                continue

            # Required status
            is_req = "[required]" in rest.lower() or raw_label.endswith("*")
            clean_label = raw_label.removesuffix("*").strip()

            # Current value extraction
            curr_val = ""
            if ":" in rest:
                val_part = rest.split(":", 1)[1].strip()
                if val_part and not val_part.startswith("["):
                    curr_val = val_part.strip('"\'')

            if ref and role in INTERACTIVE_ROLES:
                field = FormField(
                    ref=ref,
                    label=clean_label[:80],
                    role=role,
                    required=is_req,
                    options=(),
                    current_value=curr_val,
                )
                fields.append(field)
                if role in {"combobox", "listbox", "select"}:
                    parent_field_index = len(fields) - 1
                else:
                    parent_field_index = None

        return page_url, fields

    def _parse_dict_nodes(
        self, node: dict[str, Any], fields: list[FormField]
    ) -> None:
        ref = str(node.get("ref") or node.get("id") or "")
        role = str(node.get("role") or "").lower()
        label = str(
            node.get("name") or node.get("label") or node.get("description") or ""
        ).strip()
        required = bool(node.get("required") or node.get("aria-required"))
        current_value = str(node.get("value") or "").strip()

        raw_opts = node.get("options") or node.get("choices") or []
        options = tuple(str(o).strip() for o in raw_opts if str(o).strip())

        if ref and (role in INTERACTIVE_ROLES or "input" in role or "button" in role):
            clean_lbl = label.removesuffix("*").strip()
            fields.append(
                FormField(
                    ref=ref,
                    label=clean_lbl[:80],
                    role=role,
                    required=required or label.endswith("*"),
                    options=options,
                    current_value=current_value,
                )
            )

        children = node.get("children") or node.get("nodes") or []
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    self._parse_dict_nodes(child, fields)

    def _post_process(self, fields: list[FormField]) -> list[FormField]:
        seen_refs: set[str] = set()
        unique_fields: list[FormField] = []
        for f in fields:
            if f.ref not in seen_refs:
                seen_refs.add(f.ref)
                unique_fields.append(f)

        # Merge radios with same label into one field with options
        radio_groups: dict[str, list[FormField]] = {}
        final_fields: list[FormField] = []

        for f in unique_fields:
            if f.role == "radio":
                radio_groups.setdefault(f.label, []).append(f)
            else:
                final_fields.append(f)

        for lbl, radios in radio_groups.items():
            first = radios[0]
            opts = tuple(r.ref for r in radios)
            final_fields.append(
                FormField(
                    ref=first.ref,
                    label=first.label,
                    role="radio",
                    required=first.required,
                    options=opts,
                    current_value=first.current_value,
                )
            )

        return final_fields
