#!/usr/bin/env python3
"""Calculate replacement-card tier fees and policy gates from supplied live data.

Reads one JSON object on stdin and writes one JSON object on stdout. This is advisory:
callers must separately verify account/card/order eligibility with banking tools.
"""
import json
import sys
from datetime import date, datetime, timedelta


RULES = {
    "ENTRY": {
        "limit": 2,
        "delivery": {"STANDARD": 0},
        "design": {"CLASSIC": 0, "PREMIUM": 10, "CUSTOM": 25},
        "excess_fee": 25,
        "wait_hours": 48,
    },
    "MID": {
        "limit": 3,
        "delivery": {"STANDARD": 0, "EXPEDITED": 15},
        "design": {"CLASSIC": 0, "PREMIUM": 10, "CUSTOM": 25},
        "excess_fee": 15,
        "wait_hours": 0,
    },
    "PREMIUM": {
        "limit": 5,
        "delivery": {"STANDARD": 0, "EXPEDITED": 0, "RUSH": 35},
        "design": {"CLASSIC": 0, "PREMIUM": 0, "CUSTOM": 15},
        "excess_fee": None,
        "wait_hours": 0,
    },
    "ELITE": {
        "limit": None,
        "delivery": {"STANDARD": 0, "EXPEDITED": 0, "RUSH": 0},
        "design": {"CLASSIC": 0, "PREMIUM": 0, "CUSTOM": 0},
        "excess_fee": None,
        "wait_hours": 0,
    },
}


def parse_day(value, field):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be YYYY-MM-DD")


def parse_timestamp(value):
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise ValueError("closed_at must be an ISO-8601 timestamp")


def main(payload):
    tier = str(payload.get("tier", "")).upper()
    delivery = str(payload.get("delivery", "")).upper()
    design = str(payload.get("design", "")).upper()
    if tier not in RULES:
        raise ValueError("tier must be ENTRY, MID, PREMIUM, or ELITE")
    rules = RULES[tier]
    if delivery not in rules["delivery"]:
        raise ValueError(f"{delivery or 'delivery'} is not available for {tier}")
    if design not in rules["design"]:
        raise ValueError("design must be CLASSIC, PREMIUM, or CUSTOM")

    as_of = parse_day(payload.get("as_of"), "as_of")
    raw_dates = payload.get("replacement_issue_dates", [])
    if not isinstance(raw_dates, list):
        raise ValueError("replacement_issue_dates must be a list")
    # Rolling 12 months is represented by the date one calendar year earlier when valid.
    try:
        window_start = as_of.replace(year=as_of.year - 1)
    except ValueError:  # Feb 29 -> Feb 28 in a non-leap prior year
        window_start = as_of.replace(year=as_of.year - 1, day=28)
    qualifying_count = sum(window_start <= parse_day(x, "replacement_issue_dates item") <= as_of for x in raw_dates)

    reasons = []
    eligible = True
    excess_available = False
    excess_confirmed = bool(payload.get("excess_fee_confirmed", False))
    excess_fee = 0
    if rules["limit"] is not None and qualifying_count >= rules["limit"]:
        if rules["excess_fee"] is None:
            eligible = False
            reasons.append("replacement limit reached; this tier must wait for the oldest qualifying replacement to leave the rolling 12-month window")
        else:
            excess_available = True
            excess_fee = rules["excess_fee"]
            if not excess_confirmed:
                eligible = False
                reasons.append("replacement limit reached; customer must confirm the excess replacement fee or wait")

    closed_at = parse_timestamp(payload.get("closed_at"))
    wait_hours = rules["wait_hours"]
    if wait_hours:
        if closed_at is None:
            eligible = False
            reasons.append("ENTRY replacement requires the prior card closure timestamp and a 48-hour wait")
        else:
            # `as_of` is date-only, so this helper cannot establish time-of-day passage.
            # Return the earliest timestamp for the caller to compare with live current time.
            reasons.append("compare earliest_order_at with live current timestamp before ordering")

    earliest = (closed_at + timedelta(hours=wait_hours)).isoformat() if closed_at and wait_hours else None
    return {
        "tier": tier,
        "qualifying_replacements_in_rolling_12_months": qualifying_count,
        "delivery": delivery,
        "design": design,
        "delivery_fee": rules["delivery"][delivery],
        "design_fee": rules["design"][design],
        "excess_replacement_fee": excess_fee,
        "excess_fee_available": excess_available,
        "excess_fee_confirmed": excess_confirmed,
        "earliest_order_at": earliest,
        "eligible_subject_to_live_checks": eligible,
        "blocking_or_followup_reasons": reasons,
    }


if __name__ == "__main__":
    try:
        value = json.load(sys.stdin)
        if not isinstance(value, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(value), separators=(",", ":")))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
