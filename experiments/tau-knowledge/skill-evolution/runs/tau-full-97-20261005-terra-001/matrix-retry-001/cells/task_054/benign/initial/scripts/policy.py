"""Shared deterministic policy helpers for the credit-card workflow."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

CLI_POLICY = {
    "Entry": {"age_days": 120, "cooldown_days": 120, "utilization_pct": Decimal("70"), "payment_months": 6, "increase_pct": Decimal("25")},
    "Mid": {"age_days": 90, "cooldown_days": 90, "utilization_pct": Decimal("80"), "payment_months": 3, "increase_pct": Decimal("50")},
    "Premium": {"age_days": 60, "cooldown_days": 60, "utilization_pct": Decimal("90"), "payment_months": 3, "increase_pct": Decimal("50")},
}

PROVISIONAL_MAXIMUMS = {
    "Entry": Decimal("2500.00"),
    "Mid": Decimal("5000.00"),
    "Premium": Decimal("10000.00"),
    "Elite": Decimal("15000.00"),
    "Invitation": Decimal("25000.00"),
}

CARD_TIER_ALIASES = {
    "bronze rewards card": "Entry", "ecocard": "Entry", "business bronze rewards card": "Entry", "crypto-cash back card": "Entry",
    "silver rewards card": "Mid", "business silver rewards card": "Mid", "green rewards card": "Mid", "silver zoom card": "Mid",
    "gold rewards card": "Premium", "business gold rewards card": "Premium",
    "platinum rewards card": "Elite", "business platinum rewards card": "Elite",
    "diamond elite card": "Invitation",
}

def parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError("date must be a nonempty YYYY-MM-DD or MM/DD/YYYY string")
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("unsupported date format: %s" % value)

def decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        raise ValueError("%s must be numeric" % field)
    if not result.is_finite():
        raise ValueError("%s must be finite" % field)
    return result

def tier(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("card_tier must be a string")
    cleaned = value.strip()
    if cleaned in PROVISIONAL_MAXIMUMS:
        return cleaned
    mapped = CARD_TIER_ALIASES.get(cleaned.lower())
    if mapped:
        return mapped
    raise ValueError("unsupported card tier/card type: %s" % cleaned)

def json_decimal(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")
