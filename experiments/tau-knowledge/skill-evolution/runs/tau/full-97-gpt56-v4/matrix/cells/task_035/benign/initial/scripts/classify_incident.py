#!/usr/bin/env python3
"""Classify public incident facts only; this script never performs bank actions.

Reads one JSON object from stdin and writes one JSON object to stdout. Required keys:
current_time, active_start, active_end, customer_message. Dates use YYYY-MM-DD;
current_time may include a time and timezone after the date.
"""
import json
import re
import sys
from datetime import date


def parse_date_prefix(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", value.strip())
    if not match:
        raise ValueError(f"{field} must begin with YYYY-MM-DD")
    return date.fromisoformat(match.group(1))


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        current = parse_date_prefix(payload.get("current_time"), "current_time")
        start = parse_date_prefix(payload.get("active_start"), "active_start")
        end = parse_date_prefix(payload.get("active_end"), "active_end")
        if start > end:
            raise ValueError("active_start must not be after active_end")
        message = payload.get("customer_message")
        if not isinstance(message, str):
            raise ValueError("customer_message must be a string")

        normalized = message.casefold()
        patterns = {
            "credit_score_drop": r"(?:credit\s+)?score\s+(?:dropped|drop|decrease|decreased|fell|fall)",
            "delinquency_report": r"delinquen|late\s+(?:payment|report)|reported\s+.*(?:bureau|credit)",
            "credit_monitoring_alert": r"credit\s*(?:karma|monitor(?:ing)?)|alert",
            "current_payments": r"(?:never\s+missed|payments?\s+(?:are\s+)?current|autopay|paid\s+on\s+time)",
        }
        indicators = [name for name, pattern in patterns.items() if re.search(pattern, normalized)]
        # A report/alert plus either payment-current evidence or a score-drop is a
        # conservative match for an erroneous-report incident.
        report_signal = any(x in indicators for x in ("delinquency_report", "credit_monitoring_alert"))
        harm_or_current = any(x in indicators for x in ("credit_score_drop", "current_payments"))
        matches = report_signal and harm_or_current
        in_window = start <= current <= end
        print(json.dumps({
            "within_date_window": in_window,
            "matches_symptoms": matches,
            "matched_indicators": indicators,
            "applicable": in_window and matches,
        }, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
