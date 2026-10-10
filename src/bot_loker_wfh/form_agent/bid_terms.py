"""Freelance bid values: the price comes from market data, the model only writes the plan.

The amount is computed from the project's real numbers (the average bid when the platform
reports it, else the middle of the client's budget), never guessed by a language model:
a model-chosen "hourly rate" typed into a fixed-price "Bid amount" box is what made bids
far cheaper than the average.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable

DEFAULT_DURATION_DAYS = "14"
DEFAULT_WEEKLY_LIMIT = "20"
DEFAULT_MILESTONES = "1) Analisis kebutuhan & setup; 2) Implementasi fitur utama; 3) Pengujian, revisi, serah terima"
_NUMBER = r"\d+(?:\.\d+)?"


@dataclass(frozen=True)
class BidTerms:
    amount: str          # total price (fixed project) or the hourly rate (hourly project)
    hourly_rate: str
    weekly_limit: str
    duration_days: str
    milestones: str

    def as_values(self) -> dict[str, str]:
        return {
            "bid.amount": self.amount,
            "bid.hourly_rate": self.hourly_rate or self.amount,
            "bid.weekly_limit": self.weekly_limit,
            "bid.duration_days": self.duration_days,
            "bid.milestones": self.milestones,
        }

    def as_dict(self) -> dict[str, str]:
        return {"amount": self.amount, "hourly_rate": self.hourly_rate, "weekly_limit": self.weekly_limit,
                "duration_days": self.duration_days, "milestones": self.milestones}


@dataclass(frozen=True)
class Budget:
    currency: str
    low: float
    high: float | None
    hourly: bool
    bids: int | None
    average: float | None


_BUDGET = re.compile(
    r"^\s*(?P<cur>[A-Za-z]{2,3})?\s*(?P<low>[\d.,]+)\s*-\s*(?P<high>[\d.,]+|\?)\s*(?P<hourly>/hour)?"
    r"(?:\s*\|\s*(?P<bids>\d+)\s*bid)?(?:\s*\|\s*avg\s*(?P<avg>[\d.,]+))?"
)


def _num(text: str | None) -> float | None:
    try:
        return float(text.replace(",", "")) if text and text != "?" else None
    except ValueError:
        return None


def parse_budget(text: str | None) -> Budget | None:
    """Read the budget line stored on a lead, e.g. "USD 250-750 | 19 bid | avg 410"."""
    match = _BUDGET.match(text or "")
    if not match or _num(match["low"]) is None:
        return None
    return Budget(
        currency=(match["cur"] or "").upper(), low=_num(match["low"]), high=_num(match["high"]),
        hourly=bool(match["hourly"]), bids=int(match["bids"]) if match["bids"] else None, average=_num(match["avg"]),
    )


def _fmt(value: float) -> str:
    return str(int(round(value))) if value >= 20 else f"{value:.2f}".rstrip("0").rstrip(".")


def suggest_amount(budget: Budget | None) -> str:
    """Never below the average bid: the average when known, else the middle of the budget range."""
    if budget is None:
        return ""
    high = budget.high if budget.high is not None else budget.low * 1.5
    base = budget.average if budget.average else (budget.low + high) / 2
    value = min(max(base, budget.low), high)
    if value >= 100:  # tidy numbers read as deliberate, not auto-generated
        value = round(value / 5) * 5
    return _fmt(value)


def parse_bid_terms(raw: str) -> BidTerms:
    """Parse stored/model JSON; reject unsafe or non-numeric values."""
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("bid terms must be an object")
    values = {key: str(data.get(key, "") or "").strip() for key in (
        "amount", "hourly_rate", "weekly_limit", "duration_days", "milestones"
    )}
    for key in ("amount", "hourly_rate", "weekly_limit", "duration_days"):
        if values[key] and not re.fullmatch(_NUMBER, values[key]):
            raise ValueError(f"invalid {key}")
    if not values["duration_days"]:
        raise ValueError("bid terms missing required value")
    if not values["weekly_limit"]:
        values["weekly_limit"] = DEFAULT_WEEKLY_LIMIT
    if not values["milestones"] or len(values["milestones"]) > 2000:
        raise ValueError("invalid milestones")
    return BidTerms(**values)


def choose_bid_terms(
    llm: Callable[[str], str] | None, *, title: str, description: str, budget: str = "", note: str = ""
) -> BidTerms | None:
    """Price from market data; the model only picks duration, weekly hours and milestones."""
    parsed = parse_budget(budget)
    amount = suggest_amount(parsed)
    plan: dict = {}
    if llm is not None:
        prompt = (
            "Return JSON only with keys duration_days (number of days, digits only), "
            "weekly_limit (hours per week, digits only) and milestones (concise plain text, "
            "3 short steps). Do not include a price.\n"
            + (f"The owner asked for this change (follow it): {note[:500]}\n" if note else "")
            + f"Title: {title}\nBudget: {budget or '-'}\nDescription: {description[:3000]}"
        )
        try:
            data = json.loads(str(llm(prompt) or ""))
            plan = data if isinstance(data, dict) else {}
        except Exception:
            plan = {}
    if not amount and not plan:
        return None
    days = str(plan.get("duration_days") or "").strip()
    weekly = str(plan.get("weekly_limit") or "").strip()
    try:
        return parse_bid_terms(json.dumps({
            "amount": amount,
            "hourly_rate": amount if parsed and parsed.hourly else "",
            "weekly_limit": weekly if re.fullmatch(_NUMBER, weekly) else DEFAULT_WEEKLY_LIMIT,
            "duration_days": days if re.fullmatch(_NUMBER, days) else DEFAULT_DURATION_DAYS,
            "milestones": str(plan.get("milestones") or DEFAULT_MILESTONES)[:2000],
        }))
    except ValueError:
        return None
