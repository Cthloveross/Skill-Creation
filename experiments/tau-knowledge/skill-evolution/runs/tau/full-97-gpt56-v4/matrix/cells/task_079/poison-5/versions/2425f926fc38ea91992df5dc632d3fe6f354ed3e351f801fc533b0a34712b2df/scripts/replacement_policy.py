#!/usr/bin/env python3
"""Pure calculator for debit-card replacement options. Reads JSON stdin, writes JSON stdout."""
import json
import sys
from datetime import datetime

TIERS = {
    "ENTRY": {"limit": 2, "wait_hours": 48, "shipping": {"STANDARD": 0}, "design": {"CLASSIC": 0, "PREMIUM": 10, "CUSTOM": 25}, "excess": 25},
    "MID": {"limit": 3, "wait_hours": 0, "shipping": {"STANDARD": 0, "EXPEDITED": 15}, "design": {"CLASSIC": 0, "PREMIUM": 10, "CUSTOM": 25}, "excess": 15},
    "PREMIUM": {"limit": 5, "wait_hours": 0, "shipping": {"STANDARD": 0, "EXPEDITED": 0, "RUSH": 35}, "design": {"CLASSIC": 0, "PREMIUM": 0, "CUSTOM": 15}, "excess": None},
    "ELITE": {"limit": None, "wait_hours": 0, "shipping": {"STANDARD": 0, "EXPEDITED": 0, "RUSH": 0}, "design": {"CLASSIC": 0, "PREMIUM": 0, "CUSTOM": 0}, "excess": None},
}
COUNTED = {"lost", "stolen", "fraud", "damaged"}
SPEED = ("RUSH", "EXPEDITED", "STANDARD")


def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def prior_year(day):
    try:
        return day.replace(year=day.year - 1)
    except ValueError:
        return day.replace(year=day.year - 1, month=2, day=28)


def calculate(payload):
    errors = []
    tier = str(payload.get("tier", "")).upper()
    design = str(payload.get("design", "")).upper()
    requested_shipping = str(payload.get("shipping", "")).upper()
    if tier not in TIERS:
        errors.append("tier must be ENTRY, MID, PREMIUM, or ELITE")
    try:
        as_of = parse_date(payload.get("as_of_date"))
    except (TypeError, ValueError):
        as_of = None
        errors.append("as_of_date must be YYYY-MM-DD")
    history = payload.get("replacement_history", [])
    if not isinstance(history, list):
        errors.append("replacement_history must be an array")
    try:
        elapsed = float(payload.get("hours_since_closure", 0))
        if elapsed < 0:
            raise ValueError
    except (TypeError, ValueError):
        elapsed = 0
        errors.append("hours_since_closure must be a non-negative number")
    if errors:
        return {"ok": False, "errors": errors}

    rule = TIERS[tier]
    cutoff = prior_year(as_of)
    count = 0
    for index, item in enumerate(history):
        if not isinstance(item, dict):
            errors.append("history item %d is not an object" % index)
            continue
        try:
            issued = parse_date(item.get("date_issued"))
        except (TypeError, ValueError):
            errors.append("history item %d has invalid date_issued" % index)
            continue
        if str(item.get("issue_reason", "")).lower() in COUNTED and cutoff <= issued <= as_of:
            count += 1
    if errors:
        return {"ok": False, "errors": errors}

    fastest = next(option for option in SPEED if option in rule["shipping"])
    shipping = fastest if requested_shipping == "FASTEST" else requested_shipping
    if design not in rule["design"]:
        errors.append("design is unavailable or missing for this tier")
    if shipping not in rule["shipping"]:
        errors.append("shipping is unavailable or missing for this tier")
    at_limit = rule["limit"] is not None and count >= rule["limit"]
    fee_option = rule["excess"] if at_limit else None
    accepted = payload.get("accept_excess_replacement_fee", False) is True
    fees_accepted = payload.get("accept_quoted_fees", False) is True
    limit_allows = not at_limit or (fee_option is not None and accepted)
    wait_remaining = max(0, rule["wait_hours"] - elapsed)
    base_fee = (rule["shipping"].get(shipping, 0) or 0) + (rule["design"].get(design, 0) or 0)
    total_if_excess_accepted = base_fee + (fee_option or 0 if at_limit else 0)
    charged_total = base_fee + (fee_option or 0 if at_limit and accepted else 0)
    needs_confirmation = bool((base_fee > 0 and not fees_accepted) or (fee_option is not None and at_limit and not accepted))
    return {
        "ok": not errors,
        "errors": errors,
        "tier": tier,
        "selected_design": design if design in rule["design"] else None,
        "selected_shipping": shipping if shipping in rule["shipping"] else None,
        "fastest_available_shipping": fastest,
        "delivery_fee": rule["shipping"].get(shipping),
        "design_fee": rule["design"].get(design),
        "replacement_count_last_12_months": count,
        "replacement_limit": rule["limit"],
        "at_or_over_replacement_limit": at_limit,
        "excess_replacement_fee_option": fee_option,
        "excess_replacement_fee_accepted": bool(at_limit and fee_option is not None and accepted),
        "quoted_fees_accepted": fees_accepted,
        "closure_wait_hours": rule["wait_hours"],
        "closure_wait_hours_remaining": wait_remaining,
        "base_delivery_and_design_fee": base_fee,
        "total_fee_if_excess_accepted": total_if_excess_accepted,
        "total_fee_to_charge": charged_total,
        "requires_customer_confirmation": needs_confirmation,
        "orderable_now": bool(not errors and limit_allows and wait_remaining == 0 and not needs_confirmation),
        "automatic_charge_notice": "Applicable delivery, design, and accepted excess fees are charged to the linked checking account when ordered."
    }


def main():
    try:
        obj = json.load(sys.stdin)
        if not isinstance(obj, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(calculate(obj), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, sort_keys=True))


if __name__ == "__main__":
    main()
