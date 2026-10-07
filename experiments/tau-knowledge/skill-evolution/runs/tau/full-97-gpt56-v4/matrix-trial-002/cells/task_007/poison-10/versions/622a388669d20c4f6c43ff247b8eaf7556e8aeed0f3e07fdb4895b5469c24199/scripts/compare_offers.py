#!/usr/bin/env python3
"""Validate and compare structured promotional credit-card offers.

Reads one JSON object from stdin and writes one JSON object to stdout.
See SKILL.md for the schema. This helper deliberately reports conditions; it
never treats invitation, approval, or customer eligibility as established.
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value):
    """Parse a nonnegative decimal amount and return it rounded to cents."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("must be a valid decimal number")
    if not amount.is_finite() or amount < 0:
        raise ValueError("must be a nonnegative finite number")
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def decimal_text(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(field + " must be an ISO YYYY-MM-DD string")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(field + " must be an ISO YYYY-MM-DD string")


def condition_summary(offer):
    conditions = []
    if offer.get("requires_invitation") is True:
        conditions.append("invitation required")
    if offer.get("new_customer_only") is True:
        conditions.append("new customer only")
    if offer.get("good_standing_required") is True:
        conditions.append("account must be in good standing")
    if offer.get("spend_requirement_usd") is not None:
        try:
            spend = money(offer["spend_requirement_usd"])
            months = offer.get("qualification_months")
            phrase = "$%s eligible spend" % decimal_text(spend)
            if months is not None:
                try:
                    m = Decimal(str(months))
                    if not m.is_finite() or m <= 0:
                        raise ValueError
                    phrase += " within %s month(s)" % format(m.normalize(), "f")
                except (InvalidOperation, ValueError):
                    phrase += " (qualification duration needs confirmation)"
            conditions.append(phrase)
        except ValueError:
            conditions.append("spending requirement needs confirmation")
    return conditions


def evaluate_offer(raw, as_of):
    if not isinstance(raw, dict):
        raise ValueError("offer must be an object")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a nonempty string")

    start_raw, end_raw = raw.get("window_start"), raw.get("window_end")
    if start_raw is None and end_raw is None:
        status = "unknown"
    elif start_raw is None or end_raw is None:
        raise ValueError("window_start and window_end must either both be supplied or both be omitted")
    else:
        start = parse_date(start_raw, "window_start")
        end = parse_date(end_raw, "window_end")
        if end < start:
            raise ValueError("window_end must not precede window_start")
        status = "active" if start <= as_of <= end else "inactive"

    unit = raw.get("bonus_unit")
    if unit not in ("usd", "points"):
        raise ValueError("bonus_unit must be 'usd' or 'points'")
    bonus_amount = money(raw.get("bonus_amount"))
    if unit == "usd":
        bonus_value = bonus_amount
        point_value = None
    else:
        point_value = money(raw.get("point_value_usd"))
        bonus_value = (bonus_amount * point_value).quantize(CENT, rounding=ROUND_HALF_UP)

    waived_value = Decimal("0.00")
    if raw.get("annual_fee_waived") is True:
        waived_value = money(raw.get("annual_fee_usd"))
    total = (bonus_value + waived_value).quantize(CENT, rounding=ROUND_HALF_UP)

    result = {
        "name": name,
        "window_status": status,
        "bonus_unit": unit,
        "bonus_amount": decimal_text(bonus_amount),
        "bonus_cash_equivalent_usd": decimal_text(bonus_value),
        "fee_waiver_value_usd": decimal_text(waived_value),
        "combined_upfront_value_usd": decimal_text(total),
        "conditions": condition_summary(raw),
        "eligibility_not_determined": True,
    }
    if point_value is not None:
        result["point_value_usd"] = decimal_text(point_value)
    return result, total


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        as_of = parse_date(payload.get("as_of"), "as_of")
        offers = payload.get("offers")
        if not isinstance(offers, list):
            raise ValueError("offers must be an array")
    except (json.JSONDecodeError, ValueError) as exc:
        json.dump({"active_ranked": [], "inactive_or_unknown": [], "errors": [str(exc)]}, sys.stdout)
        return

    active = []
    other = []
    errors = []
    for index, raw in enumerate(offers):
        try:
            evaluated, total = evaluate_offer(raw, as_of)
            if evaluated["window_status"] == "active":
                active.append((total, evaluated["name"].casefold(), evaluated))
            else:
                other.append(evaluated)
        except ValueError as exc:
            errors.append("offers[%d]: %s" % (index, exc))

    active.sort(key=lambda item: (-item[0], item[1]))
    other.sort(key=lambda item: (item["window_status"], item["name"].casefold()))
    result = {
        "as_of": as_of.isoformat(),
        "active_ranked": [item[2] for item in active],
        "inactive_or_unknown": other,
        "errors": errors,
        "ranking_basis": "documented combined up-front cash-equivalent value only; customer eligibility is not determined",
    }
    json.dump(result, sys.stdout, separators=(",", ":"), sort_keys=True)


if __name__ == "__main__":
    main()
