#!/usr/bin/env python3
"""Render a documented no-all-fit explanation and closest-fit tradeoff from JSON."""

import json
import sys
from decimal import Decimal, InvalidOperation

REQUIRED = (
    "name",
    "overdraft_fee",
    "minimum_balance",
    "monthly_atm_rebate",
    "apy",
    "monthly_maintenance_fee",
    "maintenance_fee_waiver_balance",
)


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


def money(value):
    text = format(value, ",f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "$" + text


def compact(value):
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


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

    values = {}
    for field in REQUIRED[1:]:
        if field in payload:
            try:
                values[field] = parse_decimal(payload[field], field)
            except ValueError as exc:
                errors.append(str(exc))
    if "monthly_maintenance_fee" in values and values["monthly_maintenance_fee"] <= 0:
        errors.append("monthly_maintenance_fee must be positive for a no-fit fee explanation")

    note = payload.get("unresolved_eligibility_note")
    if note is not None and (not isinstance(note, str) or not note.strip()):
        errors.append("unresolved_eligibility_note must be a nonempty string when supplied")
    if errors:
        return {"message": None, "errors": errors}

    account = name.strip()
    lines = [
        "I cannot confirm that any documented account meets every hard requirement, including no monthly maintenance fee.",
        f"{account} is the closest documented fit for the other requirements: it has a {money(values['overdraft_fee'])} overdraft fee, a {money(values['minimum_balance'])} minimum balance requirement, up to {money(values['monthly_atm_rebate'])} per month in eligible out-of-network ATM-fee rebates, and {compact(values['apy'])}% APY.",
        f"However, I cannot present {account} as meeting all of your requirements because its monthly maintenance fee is {money(values['monthly_maintenance_fee'])}, and it is waived only at a {money(values['maintenance_fee_waiver_balance'])} balance.",
    ]
    if isinstance(note, str):
        lines.append(note.strip())
    lines.append("Would you like the closest fit despite that monthly-fee tradeoff, or would you prefer to relax a different requirement?")
    return {"message": "\n".join(lines), "errors": []}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), separators=(",", ":")))
    except json.JSONDecodeError:
        print(json.dumps({"message": None, "errors": ["stdin must contain valid JSON"]}, separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"message": None, "errors": [f"unexpected input error: {exc}"]}, separators=(",", ":")))
