"""LLM-selected freelance bid values with strict local validation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class BidTerms:
    hourly_rate: str
    weekly_limit: str
    duration_days: str
    milestones: str

    def as_values(self) -> dict[str, str]:
        return {
            "bid.hourly_rate": self.hourly_rate,
            "bid.weekly_limit": self.weekly_limit,
            "bid.duration_days": self.duration_days,
            "bid.milestones": self.milestones,
        }


def parse_bid_terms(raw: str) -> BidTerms:
    """Parse model JSON; reject missing, non-numeric, or unsafe values."""
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("bid terms must be an object")
    values = {key: str(data.get(key, "")).strip() for key in (
        "hourly_rate", "weekly_limit", "duration_days", "milestones"
    )}
    if not values["hourly_rate"] or not values["weekly_limit"] or not values["duration_days"]:
        raise ValueError("bid terms missing required value")
    for key in ("hourly_rate", "weekly_limit", "duration_days"):
        if not re.fullmatch(r"\d+(?:\.\d+)?", values[key]):
            raise ValueError(f"invalid {key}")
    if not values["milestones"] or len(values["milestones"]) > 2000:
        raise ValueError("invalid milestones")
    return BidTerms(**values)


def choose_bid_terms(llm: Callable[[str], str] | None, *, title: str, description: str, budget: str = "") -> BidTerms | None:
    if llm is None:
        return None
    prompt = (
        "Return JSON only with keys hourly_rate, weekly_limit, duration_days, milestones. "
        "Choose a reasonable competitive bid from project scope and budget. "
        "Use numeric strings for first three keys. milestones must be concise plain text. "
        "Never include currency symbols in hourly_rate.\n"
        f"Title: {title}\nBudget: {budget or '-'}\nDescription: {description[:3000]}"
    )
    try:
        return parse_bid_terms(str(llm(prompt) or ""))
    except Exception:
        return None
