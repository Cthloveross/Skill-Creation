#!/usr/bin/env python3
"""Calculate a credit-limit-increase amount and tier maximum.

Reads one JSON object from stdin and writes one JSON object to stdout. This
helper is intentionally side-effect free; it neither reads customer records
nor calls banking tools.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

RULES = {
    "entry": Decimal("0.25"),
    "mid": Decimal("0.50"),
    "premium": Decimal("0.50"),
}
ALIASES = {
    "entry": "entry", "entry-tier": "entry", "entry_tier": "entry",
    "mid": "mid", "mid-tier": "mid", "mid_tier": "mid",
    "premium": "premium", "premium-tier": "premium", "premium_tier": "premium",
}


def money_string(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def main() -> None:
    result = {
        "requested_increase_amount": None,
        "maximum_increase_amount": None,
        "new_credit_limit": None,
        "within_maximum": False,
        "errors": [],
    }
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        result["errors"].append("input must be a JSON object")
        print(json.dumps(result))
        return
    if not isinstance(data, dict):
        result["errors"].append("input must be a JSON object")
        print(json.dumps(result))
        return

    tier = str(data.get("tier", "")).strip().lower()
    tier = ALIASES.get(tier)
    if tier not in RULES:
        result["errors"].append("tier must be entry, mid, or premium")

    try:
        limit = Decimal(str(data.get("current_credit_limit")))
        if not limit.is_finite() or limit <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        result["errors"].append("current_credit_limit must be a positive number")
        limit = None

    raw_request = data.get("requested_increase")
    amount = None
    try:
        if isinstance(raw_request, str) and raw_request.strip().endswith("%"):
            percentage_text = raw_request.strip()[:-1].strip()
            percentage = Decimal(percentage_text)
            if not percentage.is_finite() or percentage <= 0 or limit is None:
                raise InvalidOperation
            amount = limit * percentage / Decimal("100")
        else:
            amount = Decimal(str(raw_request))
        if not amount.is_finite() or amount <= 0:
            raise InvalidOperation
        if amount != amount.to_integral_value():
            result["errors"].append(
                "requested increase must resolve to a positive whole-dollar amount"
            )
        else:
            amount = amount.to_integral_value()
    except (InvalidOperation, ValueError):
        result["errors"].append(
            "requested_increase must be a positive dollar amount or positive percentage"
        )

    if tier and limit is not None:
        maximum = (limit * RULES[tier]).quantize(Decimal("0.01"))
        result["maximum_increase_amount"] = money_string(maximum)
    else:
        maximum = None

    if amount is not None and amount == amount.to_integral_value():
        result["requested_increase_amount"] = int(amount)
        if limit is not None:
            result["new_credit_limit"] = money_string(limit + amount)
        if maximum is not None:
            result["within_maximum"] = amount <= maximum

    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
