#!/usr/bin/env python3
"""Classify public incident cues without collecting or exposing customer identity data."""

import json
import re
import sys
from datetime import date

START = date(2025, 11, 14)
END = date(2025, 11, 18)


def parse_calendar_date(value):
    """Return YYYY-MM-DD from a timestamp/date string, or None if unavailable."""
    if not isinstance(value, str):
        return None
    match = re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})", value)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def find_report_signals(message):
    """Return stable, non-sensitive incident categories found in a message."""
    text = (message or "").lower()
    signals = []
    if re.search(r"\b(?:credit[- ]?(?:bureau|karma|monitoring)|credit report)\b", text):
        signals.append("credit_reporting_or_monitoring")
    if re.search(r"\b(?:delinquen(?:cy|t)|late payment|past due|[0-9]+[- ]day)\b", text):
        signals.append("delinquency_report")
    if re.search(r"\b(?:credit score|score)\b.{0,60}\b(?:drop(?:ped)?|decreas(?:e|ed)|fell|fall)\b|\b(?:drop(?:ped)?|decreas(?:e|ed)|fell|fall)\b.{0,60}\b(?:credit score|score)\b", text):
        signals.append("score_decline")
    if re.search(r"\b(?:never missed|current|good standing|autopay|not incur(?:red)?)\b", text):
        signals.append("customer_denies_delinquency")
    return signals


def assess(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    current_date = parse_calendar_date(payload.get("current_time"))
    if current_date is None:
        raise ValueError("current_time must begin with a valid YYYY-MM-DD date")
    message = payload.get("customer_message", "")
    if not isinstance(message, str):
        raise ValueError("customer_message must be a string")

    in_window = START <= current_date <= END
    signals = find_report_signals(message)
    # A delinquency report or score decline coupled with credit-report context is sufficient.
    core_report = "delinquency_report" in signals or "score_decline" in signals
    related_context = "credit_reporting_or_monitoring" in signals or "customer_denies_delinquency" in signals
    matches = in_window and core_report and related_context
    return {
        "in_active_window": in_window,
        "report_signals": signals,
        "matches_incident": matches,
        "next_action": "emergency_escalate_then_transfer" if matches else "use_other_applicable_procedure",
    }


def main():
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(assess(payload), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
