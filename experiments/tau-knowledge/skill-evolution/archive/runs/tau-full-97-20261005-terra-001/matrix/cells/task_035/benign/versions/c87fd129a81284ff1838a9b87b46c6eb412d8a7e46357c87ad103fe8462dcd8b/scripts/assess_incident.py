#!/usr/bin/env python3
"""Assess whether the supplied facts match the 11/14/2025 credit-bureau incident."""
import json
import re
import sys
from datetime import datetime

START = datetime(2025, 11, 14, 0, 0, 0)
END = datetime(2025, 11, 18, 23, 59, 59)
TIME_FORMAT = "%Y-%m-%d %H:%M:%S EST"


def contains_any(text, patterns):
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def assess(payload):
    missing = []
    current_time = payload.get("current_time")
    report = payload.get("customer_report")
    parsed_time = None

    if not isinstance(current_time, str) or not current_time.strip():
        missing.append("current_time")
    else:
        try:
            parsed_time = datetime.strptime(current_time.strip(), TIME_FORMAT)
        except ValueError:
            missing.append("current_time (must be YYYY-MM-DD HH:MM:SS EST)")

    if not isinstance(report, str) or not report.strip():
        missing.append("customer_report")
        report = ""

    window_active = parsed_time is not None and START <= parsed_time <= END
    delinquency_or_bureau = contains_any(report, [
        r"credit\s*(?:bureau|karma|report(?:ing)?)",
        r"delinquen(?:cy|t)",
        r"late\s+payment",
        r"[0-9]+\s*[- ]?day\s+delinquen",
    ])
    score_or_current = contains_any(report, [
        r"credit\s*score.*(?:drop|decreas|fall)",
        r"(?:drop|decreas|fall).*(?:credit\s*)?score",
        r"score.*[0-9]+\s*point",
        r"never\s+missed",
        r"payments?\s+(?:are\s+)?current",
        r"good\s+standing",
        r"autopay",
    ])
    report_matches = bool(report.strip()) and delinquency_or_bureau and score_or_current
    applicable = not missing and window_active and report_matches

    if missing:
        reason = "insufficient_or_invalid_input"
    elif not window_active:
        reason = "outside_incident_window"
    elif not report_matches:
        reason = "report_does_not_match_incident_pattern"
    else:
        reason = "active_window_and_matching_report"

    return {
        "window_active": window_active,
        "report_matches": report_matches,
        "applicable": applicable,
        "missing_fields": missing,
        "reason": reason,
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        output = assess(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        output = {
            "window_active": False,
            "report_matches": False,
            "applicable": False,
            "missing_fields": ["valid JSON object"],
            "reason": "invalid_input: " + str(exc),
        }
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
