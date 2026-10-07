#!/usr/bin/env python3
"""Deterministic CLI amount and local threshold calculator.

Input JSON:
  tier: "entry", "mid", or "premium" (case-insensitive; optional aliases)
  current_credit_limit: positive number
  current_balance: non-negative number
  requested_increase_amount: optional positive whole-dollar number
  requested_percent: optional positive number, converted from current limit

Exactly one requested value should normally be provided. If both are supplied, they
must resolve to the same whole-dollar amount. Output JSON has either {"ok": true,
...} or {"ok": false, "error": "..."}. This utility makes no external calls.
"""
import json
import math
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

RULES = {
    "entry": {"max_fraction": Decimal("0.25"), "utilization_threshold": Decimal("70"), "min_age_days": 120, "cooldown_days": 120, "payment_months": 6},
    "mid": {"max_fraction": Decimal("0.50"), "utilization_threshold": Decimal("80"), "min_age_days": 90, "cooldown_days": 90, "payment_months": 3},
    "premium": {"max_fraction": Decimal("0.50"), "utilization_threshold": Decimal("90"), "min_age_days": 60, "cooldown_days": 60, "payment_months": 3},
}
ALIASES = {
    "entry-tier": "entry", "entry tier": "entry", "bronze rewards card": "entry",
    "mid-tier": "mid", "mid tier": "mid", "premium-tier": "premium", "premium tier": "premium",
}


def number(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be numeric")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def whole_dollars(value, field):
    rounded = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if value != rounded:
        raise ValueError(f"{field} must resolve to a whole-dollar amount")
    if rounded <= 0:
        raise ValueError(f"{field} must be greater than zero")
    return rounded


def main(payload):
    raw_tier = str(payload.get("tier", "")).strip().lower()
    tier = ALIASES.get(raw_tier, raw_tier)
    if tier not in RULES:
        raise ValueError("tier must be entry, mid, or premium")
    limit = number(payload.get("current_credit_limit"), "current_credit_limit")
    balance = number(payload.get("current_balance"), "current_balance")
    if limit <= 0:
        raise ValueError("current_credit_limit must be greater than zero")
    if balance < 0:
        raise ValueError("current_balance must not be negative")

    has_amount = payload.get("requested_increase_amount") is not None
    has_percent = payload.get("requested_percent") is not None
    if has_amount == has_percent:
        raise ValueError("supply exactly one of requested_increase_amount or requested_percent")
    if has_amount:
        amount = whole_dollars(number(payload["requested_increase_amount"], "requested_increase_amount"), "requested_increase_amount")
    else:
        percent = number(payload["requested_percent"], "requested_percent")
        if percent <= 0:
            raise ValueError("requested_percent must be greater than zero")
        amount = whole_dollars(limit * percent / Decimal("100"), "requested_percent")

    rule = RULES[tier]
    max_increase = (limit * rule["max_fraction"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    utilization = (balance / limit * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "ok": True,
        "tier": tier,
        "requested_increase_amount": int(amount),
        "maximum_increase_amount": float(max_increase),
        "amount_within_limit": amount <= max_increase,
        "new_credit_limit": float(limit + amount),
        "utilization_percent": float(utilization),
        "utilization_threshold_percent": float(rule["utilization_threshold"]),
        "utilization_eligible": utilization < rule["utilization_threshold"],
        "minimum_account_age_days": rule["min_age_days"],
        "cooldown_days": rule["cooldown_days"],
        "required_payment_months": rule["payment_months"],
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))
        sys.exit(1)
