#!/usr/bin/env python3
"""Render a complete, explicit business-checking recommendation from JSON."""

import json
import sys
from decimal import Decimal, InvalidOperation

REQUIRED = ("name", "overdraft_fee", "minimum_balance", "monthly_atm_rebate", "apy")
OPTIONAL_PAIR = ("monthly_maintenance_fee", "maintenance_fee_waiver_balance")


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


def compact(value):
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def money(value):
    return "$" + compact(value)


def main(payload):
    if not isinstance(payload, dict):
        return {"message": None, "errors": ["input must be a JSON object"]}

    errors = []
    for field in REQUIRED:
        if field not in payload:
            errors.append(f"missing required field: {field}")
    name = payload.get("name")
    if "name" in payload and (not isinstance(name, str) or not name.strip()):
        errors.append("name must be a nonempty string")

    has_fee = "monthly_maintenance_fee" in payload
    has_waiver = "maintenance_fee_waiver_balance" in payload
    if has_fee != has_waiver:
        errors.append("monthly_maintenance_fee and maintenance_fee_waiver_balance must be supplied together")

    values = {}
    for field in REQUIRED[1:] + OPTIONAL_PAIR:
        if field in payload:
            try:
                values[field] = parse_decimal(payload[field], field)
            except ValueError as exc:
                errors.append(str(exc))

    note = payload.get("higher_priority_note")
    if note is not None and (not isinstance(note, str) or not note.strip()):
        errors.append("higher_priority_note must be a nonempty string when supplied")
    if errors:
        return {"message": None, "errors": errors}

    lines = [
        f"I recommend {name.strip()}.",
        f"- Its overdraft fee is {money(values['overdraft_fee'])}.",
        f"- Its minimum balance requirement is {money(values['minimum_balance'])}.",
        f"- It provides up to {money(values['monthly_atm_rebate'])} per month in eligible out-of-network ATM-fee rebates.",
        f"- It earns {compact(values['apy'])}% APY.",
    ]
    if has_fee:
        lines.append(
            f"- Important tradeoff: its monthly maintenance fee is {money(values['monthly_maintenance_fee'])}; the fee is waived only when the balance meets {money(values['maintenance_fee_waiver_balance'])}."
        )
    if isinstance(note, str):
        lines.append(note.strip())
    return {"message": "\n".join(lines), "errors": []}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), separators=(",", ":")))
    except json.JSONDecodeError:
        print(json.dumps({"message": None, "errors": ["stdin must contain valid JSON"]}, separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"message": None, "errors": [f"unexpected input error: {exc}"]}, separators=(",", ":")))
