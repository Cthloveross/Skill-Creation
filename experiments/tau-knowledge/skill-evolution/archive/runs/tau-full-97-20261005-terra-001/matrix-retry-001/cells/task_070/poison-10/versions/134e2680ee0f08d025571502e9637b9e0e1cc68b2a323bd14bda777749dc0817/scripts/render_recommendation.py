#!/usr/bin/env python3
"""Render a complete, explicit four-constraint checking recommendation."""

import json
import sys
from decimal import Decimal, InvalidOperation

REQUIRED = ("name", "overdraft_fee", "minimum_balance", "monthly_atm_rebate", "apy")


def parse_decimal(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a non-negative decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a non-negative decimal")
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be a non-negative decimal")
    return result


def display_money(value):
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "$" + text


def main(payload):
    if not isinstance(payload, dict):
        return {"message": None, "errors": ["input must be a JSON object"]}
    errors = []
    for key in REQUIRED:
        if key not in payload:
            errors.append(f"missing required field: {key}")
    name = payload.get("name")
    if "name" in payload and (not isinstance(name, str) or not name.strip()):
        errors.append("name must be a nonempty string")
    notes = {}
    for key in ("higher_priority_note", "tradeoff"):
        value = payload.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            errors.append(f"{key} must be a nonempty string when supplied")
        elif isinstance(value, str):
            notes[key] = value.strip()
    numeric = {}
    for key in REQUIRED[1:]:
        if key in payload:
            try:
                numeric[key] = parse_decimal(payload[key], key)
            except ValueError as exc:
                errors.append(str(exc))
    if errors:
        return {"message": None, "errors": errors}

    lines = [
        f"I recommend {name.strip()}.",
        f"- Its overdraft fee is {display_money(numeric['overdraft_fee'])}.",
        f"- Its minimum balance requirement is {display_money(numeric['minimum_balance'])}.",
        f"- It provides up to {display_money(numeric['monthly_atm_rebate'])} per month in eligible out-of-network ATM-fee rebates.",
        f"- It earns {format(numeric['apy'], 'f')}% APY.",
    ]
    if "higher_priority_note" in notes:
        lines.append(notes["higher_priority_note"])
    if "tradeoff" in notes:
        lines.append(notes["tradeoff"])
    return {"message": "\n".join(lines), "errors": []}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), separators=(",", ":")))
    except json.JSONDecodeError:
        print(json.dumps({"message": None, "errors": ["stdin must contain valid JSON"]}, separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"message": None, "errors": [f"unexpected input error: {exc}"]}, separators=(",", ":")))
