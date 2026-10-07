#!/usr/bin/env python3
"""Advisory replacement-card quote calculator.

Read one JSON object from stdin and write one JSON object to stdout. The helper
never contacts banking systems and does not authorize or place an order.
"""
import json
import sys
from datetime import date, datetime, timedelta

RULES = {
    "ENTRY": {"limit": 2, "delivery": {"STANDARD": 0}, "design": {"CLASSIC": 0, "PREMIUM": 10, "CUSTOM": 25}, "excess_fee": 25, "wait_hours": 48},
    "MID": {"limit": 3, "delivery": {"STANDARD": 0, "EXPEDITED": 15}, "design": {"CLASSIC": 0, "PREMIUM": 10, "CUSTOM": 25}, "excess_fee": 15, "wait_hours": 0},
    "PREMIUM": {"limit": 5, "delivery": {"STANDARD": 0, "EXPEDITED": 0, "RUSH": 35}, "design": {"CLASSIC": 0, "PREMIUM": 0, "CUSTOM": 15}, "excess_fee": None, "wait_hours": 0},
    "ELITE": {"limit": None, "delivery": {"STANDARD": 0, "EXPEDITED": 0, "RUSH": 0}, "design": {"CLASSIC": 0, "PREMIUM": 0, "CUSTOM": 0}, "excess_fee": None, "wait_hours": 0},
}

def parse_day(value, field):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be YYYY-MM-DD")

def parse_time(value, field):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise ValueError(f"{field} must be an ISO-8601 timestamp")
    if result.tzinfo is None:
        raise ValueError(f"{field} must include a UTC offset")
    return result

def main(p):
    tier = str(p.get("tier", "")).upper()
    delivery, design = str(p.get("delivery", "")).upper(), str(p.get("design", "")).upper()
    if tier not in RULES:
        raise ValueError("tier must be ENTRY, MID, PREMIUM, or ELITE")
    rule = RULES[tier]
    if delivery not in rule["delivery"]:
        raise ValueError(f"{delivery or 'delivery'} is not available for {tier}")
    if design not in rule["design"]:
        raise ValueError("design must be CLASSIC, PREMIUM, or CUSTOM")
    as_of = parse_day(p.get("as_of"), "as_of")
    dates = p.get("replacement_issue_dates", [])
    if not isinstance(dates, list):
        raise ValueError("replacement_issue_dates must be a list")
    try:
        window_start = as_of.replace(year=as_of.year - 1)
    except ValueError:
        window_start = as_of.replace(year=as_of.year - 1, day=28)
    count = sum(window_start <= parse_day(x, "replacement_issue_dates item") <= as_of for x in dates)
    eligible, reasons, excess_available, excess_fee = True, [], False, 0
    if rule["limit"] is not None and count >= rule["limit"]:
        if rule["excess_fee"] is None:
            eligible = False
            reasons.append("replacement limit reached; wait for the oldest qualifying replacement to leave the rolling 12-month window")
        else:
            excess_available, excess_fee = True, rule["excess_fee"]
            if not bool(p.get("excess_fee_confirmed", False)):
                eligible = False
                reasons.append("replacement limit reached; customer must confirm the excess replacement fee or wait")
    earliest = None
    if rule["wait_hours"]:
        closed_at, now = p.get("closed_at"), p.get("now")
        if not closed_at or not now:
            eligible = False
            reasons.append("ENTRY replacement requires closure and current timestamps to verify the 48-hour wait")
        else:
            earliest_time = parse_time(closed_at, "closed_at") + timedelta(hours=rule["wait_hours"])
            now_time = parse_time(now, "now")
            if now_time < earliest_time:
                eligible = False
                reasons.append("ENTRY 48-hour post-closure wait has not elapsed")
            earliest = earliest_time.isoformat()
    return {"tier": tier, "qualifying_replacements_in_rolling_12_months": count, "delivery": delivery, "design": design, "delivery_fee": rule["delivery"][delivery], "design_fee": rule["design"][design], "excess_replacement_fee": excess_fee, "excess_fee_available": excess_available, "excess_fee_confirmed": bool(p.get("excess_fee_confirmed", False)), "earliest_order_at": earliest, "eligible_subject_to_live_checks": eligible, "blocking_or_followup_reasons": reasons}

if __name__ == "__main__":
    try:
        value = json.load(sys.stdin)
        if not isinstance(value, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(value), separators=(",", ":")))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(2)
