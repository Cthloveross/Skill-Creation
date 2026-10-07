#!/usr/bin/env python3
"""Calculate purchase-reward scenarios from JSON on stdin.

Input:
{
  "purchase_amount": decimal-string-or-number,
  "options": [{
    "name": string,
    "cashback_rate_percent": decimal-string-or-number,
    "first_year_annual_fee": decimal-string-or-number (optional),
    "classification": string (optional),
    "assumptions": [string, ...] (optional)
  }, ...]
}

When first_year_annual_fee is omitted or null, gross cash back is calculated but
first_year_net_value is null; that option is excluded from the net-value ranking.
Output: {"purchase_amount", "scenarios", "ranking", "unranked_options"}.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
HUNDRED = Decimal("100")


def decimal_value(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a decimal number, not a boolean")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a valid decimal number")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def money(value):
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    amount = decimal_value(payload.get("purchase_amount"), "purchase_amount")
    if amount < 0:
        raise ValueError("purchase_amount must be nonnegative")
    options = payload.get("options")
    if not isinstance(options, list) or not options:
        raise ValueError("options must be a nonempty list")

    scenarios = []
    for index, option in enumerate(options):
        if not isinstance(option, dict):
            raise ValueError(f"options[{index}] must be an object")
        name = option.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"options[{index}].name must be a nonempty string")
        rate = decimal_value(option.get("cashback_rate_percent"),
                             f"options[{index}].cashback_rate_percent")
        if rate < 0 or rate > HUNDRED:
            raise ValueError(f"options[{index}].cashback_rate_percent must be between 0 and 100")
        classification = option.get("classification", "unspecified")
        assumptions = option.get("assumptions", [])
        if not isinstance(classification, str):
            raise ValueError(f"options[{index}].classification must be a string")
        if not isinstance(assumptions, list) or not all(isinstance(x, str) for x in assumptions):
            raise ValueError(f"options[{index}].assumptions must be a list of strings")

        raw_fee = option.get("first_year_annual_fee")
        fee_known = raw_fee is not None
        fee = None
        if fee_known:
            fee = decimal_value(raw_fee, f"options[{index}].first_year_annual_fee")
            if fee < 0:
                raise ValueError(f"options[{index}].first_year_annual_fee must be nonnegative")

        gross = (amount * rate / HUNDRED).quantize(CENT, rounding=ROUND_HALF_UP)
        net = (gross - fee).quantize(CENT, rounding=ROUND_HALF_UP) if fee_known else None
        scenarios.append({
            "name": name,
            "cashback_rate_percent": str(rate),
            "first_year_annual_fee": money(fee) if fee_known else None,
            "gross_cash_back": money(gross),
            "first_year_net_value": money(net) if net is not None else None,
            "stored_points_equivalent": str((gross * HUNDRED).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
            "classification": classification,
            "assumptions": assumptions,
        })

    ranked = [item for item in scenarios if item["first_year_net_value"] is not None]
    ranked.sort(key=lambda item: (Decimal(item["first_year_net_value"]),
                                  Decimal(item["gross_cash_back"])), reverse=True)
    unranked = [item["name"] for item in scenarios if item["first_year_net_value"] is None]
    return {
        "purchase_amount": money(amount),
        "scenarios": scenarios,
        "ranking": [item["name"] for item in ranked],
        "unranked_options": unranked,
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            raise ValueError("expected JSON input on stdin")
        print(json.dumps(main(json.loads(raw)), separators=(",", ":")))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(2)
