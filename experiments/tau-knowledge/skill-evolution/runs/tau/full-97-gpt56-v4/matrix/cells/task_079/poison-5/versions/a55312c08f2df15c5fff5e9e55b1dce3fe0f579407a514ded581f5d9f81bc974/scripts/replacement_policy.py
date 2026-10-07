#!/usr/bin/env python3
"""Pure debit-card replacement policy calculator. Reads one JSON object from stdin."""
import json
import sys
from datetime import date, datetime

TIERS = {
    "ENTRY": {"limit": 2, "wait_hours": 48, "shipping": {"STANDARD": 0}, "design": {"CLASSIC": 0, "PREMIUM": 10, "CUSTOM": 25}, "excess_fee": 25},
    "MID": {"limit": 3, "wait_hours": 0, "shipping": {"STANDARD": 0, "EXPEDITED": 15}, "design": {"CLASSIC": 0, "PREMIUM": 10, "CUSTOM": 25}, "excess_fee": 15},
    "PREMIUM": {"limit": 5, "wait_hours": 0, "shipping": {"STANDARD": 0, "EXPEDITED": 0, "RUSH": 35}, "design": {"CLASSIC": 0, "PREMIUM": 0, "CUSTOM": 15}, "excess_fee": None},
    "ELITE": {"limit": None, "wait_hours": 0, "shipping": {"STANDARD": 0, "EXPEDITED": 0, "RUSH": 0}, "design": {"CLASSIC": 0, "PREMIUM": 0, "CUSTOM": 0}, "excess_fee": None},
}
COUNTED_REASONS = {"lost", "stolen", "fraud", "damaged"}
SPEED_ORDER = ("RUSH", "EXPEDITED", "STANDARD")


def parse_day(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def one_year_before(day):
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # Feb 29
        return day.replace(year=day.year - 1, month=2, day=28)


def main(payload):
    errors = []
    tier = str(payload.get("tier", "")).upper()
    design = str(payload.get("design", "")).upper()
    shipping = str(payload.get("shipping", "")).upper()
    if tier not in TIERS:
        errors.append("tier must be ENTRY, MID, PREMIUM, or ELITE")
    try:
        as_of = parse_day(payload.get("as_of_date", ""))
    except (TypeError, ValueError):
        as_of = None
        errors.append("as_of_date must be YYYY-MM-DD")
    if errors:
        return {"ok": False, "errors": errors}

    rule = TIERS[tier]
    history = payload.get("replacement_history", [])
    if not isinstance(history, list):
        return {"ok": False, "errors": ["replacement_history must be an array"]}
    cutoff = one_year_before(as_of)
    counted = 0
    history_errors = []
    for index, card in enumerate(history):
        if not isinstance(card, dict):
            history_errors.append("history item %d is not an object" % index)
            continue
        reason = str(card.get("issue_reason", "")).lower()
        try:
            issued = parse_day(card.get("date_issued", ""))
        except (TypeError, ValueError):
            history_errors.append("history item %d has invalid date_issued" % index)
            continue
        if reason in COUNTED_REASONS and cutoff <= issued <= as_of:
            counted += 1
    if history_errors:
        return {"ok": False, "errors": history_errors}

    if shipping == "FASTEST":
        shipping = next(speed for speed in SPEED_ORDER if speed in rule["shipping"])
    if design not in rule["design"]:
        errors.append("design is unavailable or missing for this calculation")
    if shipping not in rule["shipping"]:
        errors.append("shipping is unavailable or missing for this tier")
    within_limit = rule["limit"] is None or counted < rule["limit"]
    if not within_limit and rule["excess_fee"] is None:
        limit_message = "replacement limit reached; this tier must wait for history to age out"
    elif not within_limit:
        limit_message = "replacement limit reached; customer may wait or consent to the excess replacement fee"
    else:
        limit_message = None
    return {
        "ok": not errors,
        "errors": errors,
        "tier": tier,
        "selected_design": design if design in rule["design"] else None,
        "selected_shipping": shipping if shipping in rule["shipping"] else None,
        "delivery_fee": rule["shipping"].get(shipping),
        "design_fee": rule["design"].get(design),
        "replacement_count_last_12_months": counted,
        "replacement_limit": rule["limit"],
        "within_replacement_limit": within_limit,
        "excess_replacement_fee_option": rule["excess_fee"] if not within_limit else None,
        "closure_wait_hours": rule["wait_hours"],
        "orderable_now": bool(not errors and within_limit and rule["wait_hours"] == 0),
        "limit_message": limit_message,
        "automatic_charge_notice": "Quoted applicable fees are automatically charged to the linked checking account when ordered."
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, sort_keys=True))
