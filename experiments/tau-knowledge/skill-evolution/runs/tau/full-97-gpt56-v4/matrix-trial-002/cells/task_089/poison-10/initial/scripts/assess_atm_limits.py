#!/usr/bin/env python3
"""Assess ATM-limit arithmetic from JSON stdin without accessing bank systems.

Input:
  {"attempts": [{"label": str, "requested_amount": decimal|str|null,
                  "daily_atm_limit": decimal|str|null,
                  "daily_atm_used": decimal|str|null}, ...]}
Output:
  {"assessments": [{"label": str, "requested_amount": str|null,
                      "daily_atm_limit": str|null, "daily_atm_used": str|null,
                      "remaining_limit": str|null,
                      "exceeds_remaining_limit": bool|null,
                      "missing_fields": [str, ...], "note": str}]}

A null comparison means there is not enough data to determine whether the
request exceeds the remaining bank limit. This program never determines why a
transaction declined and never performs a banking action.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MONEY = Decimal("0.01")


def parse_money(value, field, index):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"attempt {index}: {field} must be a decimal amount or null")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"attempt {index}: {field} is not a valid decimal amount")
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"attempt {index}: {field} must be a non-negative finite amount")
    return parsed.quantize(MONEY, rounding=ROUND_HALF_UP)


def money_text(value):
    return None if value is None else format(value, ".2f")


def assess(item, index):
    if not isinstance(item, dict):
        raise ValueError(f"attempt {index} must be an object")
    label = item.get("label")
    if not isinstance(label, str) or not label.strip():
        raise ValueError(f"attempt {index}: label must be a non-empty string")

    request = parse_money(item.get("requested_amount"), "requested_amount", index)
    limit = parse_money(item.get("daily_atm_limit"), "daily_atm_limit", index)
    used = parse_money(item.get("daily_atm_used"), "daily_atm_used", index)
    missing = [name for name, value in (
        ("requested_amount", request),
        ("daily_atm_limit", limit),
        ("daily_atm_used", used),
    ) if value is None]

    remaining = None
    exceeds = None
    if limit is not None and used is not None:
        remaining = max(limit - used, Decimal("0.00"))
    if request is not None and remaining is not None:
        exceeds = request > remaining

    if exceeds is True:
        note = "The request exceeds the calculated remaining bank daily ATM limit. Other conditions may also apply."
    elif exceeds is False:
        note = "The request is within the calculated remaining bank daily ATM limit, but that does not establish approval or the decline reason."
    else:
        note = "There is not enough information to compare the request with the remaining bank daily ATM limit."

    return {
        "label": label,
        "requested_amount": money_text(request),
        "daily_atm_limit": money_text(limit),
        "daily_atm_used": money_text(used),
        "remaining_limit": money_text(remaining),
        "exceeds_remaining_limit": exceeds,
        "missing_fields": missing,
        "note": note,
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("attempts"), list):
            raise ValueError("input must be an object with an attempts array")
        print(json.dumps({"assessments": [assess(item, i) for i, item in enumerate(payload["attempts"], 1)]}))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
