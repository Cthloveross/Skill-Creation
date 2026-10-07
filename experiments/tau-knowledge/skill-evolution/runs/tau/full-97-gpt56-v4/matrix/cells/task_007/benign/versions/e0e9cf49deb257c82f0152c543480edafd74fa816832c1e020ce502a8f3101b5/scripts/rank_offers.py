#!/usr/bin/env python3
"""Filter and rank structured, currently confirmed credit-card signup offers.

Reads the JSON schema documented in SKILL.md from stdin and writes JSON to stdout.
No network access or external packages are required.
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def fail(message):
    print(json.dumps({"error": message}, sort_keys=True))
    raise SystemExit(2)


def parse_date(value, field, offer_name):
    if value is None:
        return None
    if not isinstance(value, str):
        fail(f"{field} for {offer_name} must be YYYY-MM-DD or null")
    try:
        return date.fromisoformat(value)
    except ValueError:
        fail(f"{field} for {offer_name} must be YYYY-MM-DD or null")


def decimal_value(value, field, offer_name, allow_null=False):
    if value is None and allow_null:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        fail(f"{field} for {offer_name} must be numeric")
    if not result.is_finite() or result < 0:
        fail(f"{field} for {offer_name} must be a non-negative finite number")
    return result


def money_string(value):
    return format(value.quantize(Decimal("0.01")), "f")


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        fail("stdin must contain one JSON object")
    if not isinstance(payload, dict) or not isinstance(payload.get("offers"), list):
        fail("input must be an object with an offers array")
    try:
        as_of = date.fromisoformat(payload["as_of"])
    except (KeyError, TypeError, ValueError):
        fail("as_of must be YYYY-MM-DD")

    eligible = []
    excluded = []
    for raw in payload["offers"]:
        if not isinstance(raw, dict):
            fail("each offer must be an object")
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            fail("each offer needs a nonempty name")
        kind = raw.get("bonus_kind")
        if kind not in {"cash", "statement_credit", "points"}:
            fail(f"bonus_kind for {name} must be cash, statement_credit, or points")
        amount = decimal_value(raw.get("bonus_amount"), "bonus_amount", name)
        start = parse_date(raw.get("start_date"), "start_date", name)
        end = parse_date(raw.get("end_date"), "end_date", name)
        if start and end and start > end:
            fail(f"start_date for {name} cannot be after end_date")

        reason = None
        if not raw.get("terms_confirmed", False):
            reason = raw.get("exclusion_reason") or "material offer terms are not confirmed"
        elif not raw.get("customer_can_apply", False):
            reason = raw.get("exclusion_reason") or "not currently accessible to the customer"
        elif start is not None and as_of < start:
            reason = raw.get("exclusion_reason") or "offer has not started"
        elif end is not None and as_of > end:
            reason = raw.get("exclusion_reason") or "offer has expired"

        if reason:
            excluded.append({"name": name, "reason": str(reason)})
            continue

        if kind == "points":
            point_value = decimal_value(raw.get("point_value_dollars"), "point_value_dollars", name)
            dollar_value = amount * point_value
        else:
            dollar_value = amount

        spend = decimal_value(raw.get("spend_requirement_dollars"), "spend_requirement_dollars", name, allow_null=True)
        days = raw.get("qualification_days")
        if days is not None and (not isinstance(days, int) or isinstance(days, bool) or days < 0):
            fail(f"qualification_days for {name} must be a non-negative integer or null")
        eligible.append({
            "name": name,
            "bonus_kind": kind,
            "bonus_amount": str(amount),
            "bonus_value_dollars": money_string(dollar_value),
            "spend_requirement_dollars": None if spend is None else money_string(spend),
            "qualification_days": days,
            "start_date": raw.get("start_date"),
            "end_date": raw.get("end_date"),
        })

    infinity = Decimal("Infinity")
    eligible.sort(key=lambda item: (
        -Decimal(item["bonus_value_dollars"]),
        infinity if item["spend_requirement_dollars"] is None else Decimal(item["spend_requirement_dollars"]),
        float("inf") if item["qualification_days"] is None else item["qualification_days"],
        item["name"].casefold(),
    ))
    print(json.dumps({"as_of": as_of.isoformat(), "eligible_ranked": eligible, "excluded": excluded}, sort_keys=True))


if __name__ == "__main__":
    main()
