#!/usr/bin/env python3
"""Classify eligibility for a payment-reflection incident protocol.

Input JSON:
  now: incident-check timestamp in ISO-like form (required)
  incident_end: end timestamp in ISO-like form (required)
  paid_statement: boolean (required)
  deducted_from_checking: boolean (required)
  missing_from_statement_balance: boolean (required)

Output JSON:
  symptoms_match, window_active, incident_applies, missing_inputs, error

The parser accepts timestamps such as "YYYY-MM-DD HH:MM:SS EST". Timezone labels
are treated as labels; callers should supply both timestamps in the same timezone.
"""
import json
import re
import sys
from datetime import datetime


def parse_timestamp(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    # Strip a final alphabetic timezone token because both supplied values must share it.
    value = re.sub(r"\s+[A-Za-z]{2,5}$", "", value)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"error": "invalid JSON input: " + str(exc)}))
        return

    flags = ["paid_statement", "deducted_from_checking", "missing_from_statement_balance"]
    missing = [key for key in flags if key not in data or not isinstance(data.get(key), bool)]
    symptoms_match = not missing and all(data[key] for key in flags)

    now = parse_timestamp(data.get("now"))
    end = parse_timestamp(data.get("incident_end"))
    if now is None:
        missing.append("now (valid timestamp)")
    if end is None:
        missing.append("incident_end (valid timestamp)")
    window_active = None if now is None or end is None else now <= end

    result = {
        "symptoms_match": symptoms_match,
        "window_active": window_active,
        "incident_applies": bool(symptoms_match and window_active is True),
        "missing_inputs": missing,
        "error": None,
    }
    if window_active is None:
        result["error"] = "Cannot assess incident window: supply parseable now and incident_end timestamps."
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
