#!/usr/bin/env python3
"""Compare documented savings/card combinations from JSON stdin.

Input:
{
  "principal": number >= 0,
  "horizon_days": positive number (optional; default 365),
  "candidates": [
    {
      "name": string,
      "base_apy_pct": number,
      "card_bonus_apy_pct": number (optional, default 0),
      "checking_bonus_apy_pct": number (optional, default 0),
      "other_bonus_apy_pct": number (optional, default 0),
      "annual_fees": number (optional, default 0),
      "one_time_fees": number (optional, default 0),
      "minimum_opening_deposit": number (optional),
      "minimum_ongoing_balance": number (optional),
      "opening_requirement_met": boolean (optional),
      "ongoing_requirement_met": boolean (optional)
    }
  ]
}

Output includes arithmetic projections and a descending feasible ranking. APY is
used as a transparent annualized estimate, not a daily-balance interest simulation.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def dec(value, field, default=None):
    if value is None:
        if default is not None:
            return default
        raise ValueError(f"missing {field}")
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        answer = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be numeric")
    if not answer.is_finite():
        raise ValueError(f"{field} must be finite")
    return answer


def money(value):
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def main(payload):
    principal = dec(payload.get("principal"), "principal")
    days = dec(payload.get("horizon_days", 365), "horizon_days")
    if principal < 0 or days <= 0:
        raise ValueError("principal must be nonnegative and horizon_days must be positive")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidates must be a nonempty array")

    result = []
    for index, item in enumerate(candidates):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            raise ValueError(f"candidate {index} needs a nonempty name")
        base = dec(item.get("base_apy_pct"), f"candidates[{index}].base_apy_pct")
        card = dec(item.get("card_bonus_apy_pct", 0), "card_bonus_apy_pct")
        checking = dec(item.get("checking_bonus_apy_pct", 0), "checking_bonus_apy_pct")
        other = dec(item.get("other_bonus_apy_pct", 0), "other_bonus_apy_pct")
        annual_fees = dec(item.get("annual_fees", 0), "annual_fees")
        one_time_fees = dec(item.get("one_time_fees", 0), "one_time_fees")
        if min(base, card, checking, other, annual_fees, one_time_fees) < 0:
            raise ValueError(f"candidate {index} contains a negative rate or fee")
        combined = base + card + checking + other
        gross = principal * (combined / Decimal("100")) * (days / Decimal("365"))
        fees = annual_fees * (days / Decimal("365")) + one_time_fees
        opening_ok = item.get("opening_requirement_met", True)
        ongoing_ok = item.get("ongoing_requirement_met", True)
        if not isinstance(opening_ok, bool) or not isinstance(ongoing_ok, bool):
            raise ValueError("requirement flags must be boolean")
        feasible = opening_ok and ongoing_ok
        entry = {
            "name": item["name"],
            "feasible": feasible,
            "combined_apy_pct": str(combined),
            "estimated_gross_interest": money(gross),
            "estimated_fees": money(fees),
            "estimated_net_return": money(gross - fees),
            "assumptions": {
                "principal": money(principal),
                "horizon_days": str(days),
                "annual_fees_prorated": True,
                "daily_balance_simulation": False,
            },
        }
        result.append(entry)
    ranked = sorted(
        (entry for entry in result if entry["feasible"]),
        key=lambda entry: Decimal(entry["estimated_net_return"]),
        reverse=True,
    )
    return {"candidates": result, "feasible_ranking": [entry["name"] for entry in ranked]}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(1)
