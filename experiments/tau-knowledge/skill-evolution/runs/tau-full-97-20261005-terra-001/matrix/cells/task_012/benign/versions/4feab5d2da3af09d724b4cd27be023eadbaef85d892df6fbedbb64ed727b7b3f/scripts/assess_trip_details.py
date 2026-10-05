#!/usr/bin/env python3
"""Assess whether travel dates are complete without deciding bank policy.

Input JSON object:
  {
    "destination": "optional string",
    "dates_confirmed": true|false,
    "departure_date": "YYYY-MM-DD (required when dates_confirmed is true)",
    "return_date": "YYYY-MM-DD (required when dates_confirmed is true)",
    "trip_timing": "optional free-text description"
  }

Output JSON object contains:
  ok: whether the provided date representation is internally valid
  date_status: dates_not_final, dates_complete, or invalid_date_details
  missing_fields: required fields not supplied for a claimed-final itinerary
  response_constraints: safeguards for the customer-facing response

This helper intentionally does not calculate dates from relative phrases, decide whether
travel-notification dates are required, or invoke any banking tools.
"""

import datetime as dt
import json
import sys


def is_nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def parse_iso_date(value):
    if not is_nonempty_string(value):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        print(json.dumps({"ok": False, "error": "Input must be a JSON object."}))
        return

    if not isinstance(payload, dict):
        print(json.dumps({"ok": False, "error": "Input must be a JSON object."}))
        return

    confirmed = payload.get("dates_confirmed")
    if not isinstance(confirmed, bool):
        print(json.dumps({
            "ok": False,
            "error": "dates_confirmed must be a boolean.",
            "response_constraints": [
                "Do not infer a finalized itinerary from a relative timing phrase."
            ]
        }))
        return

    base_constraints = [
        "Do not state that exact dates are optional or mandatory for a travel notification unless a documented account policy establishes that.",
        "Do not claim that a notification was submitted or that travel transactions will be approved."
    ]

    if not confirmed:
        print(json.dumps({
            "ok": True,
            "date_status": "dates_not_final",
            "missing_fields": ["departure_date", "return_date"],
            "destination_provided": is_nonempty_string(payload.get("destination")),
            "response_constraints": base_constraints + [
                "Explain that the supplied material does not resolve whether the notification flow can proceed before dates are finalized."
            ]
        }))
        return

    missing = [field for field in ("departure_date", "return_date")
               if not is_nonempty_string(payload.get(field))]
    departure = parse_iso_date(payload.get("departure_date"))
    returning = parse_iso_date(payload.get("return_date"))

    if missing or departure is None or returning is None or returning < departure:
        details = []
        if not missing and (departure is None or returning is None):
            details.append("Dates must use YYYY-MM-DD.")
        if departure is not None and returning is not None and returning < departure:
            details.append("return_date cannot be before departure_date.")
        print(json.dumps({
            "ok": False,
            "date_status": "invalid_date_details",
            "missing_fields": missing,
            "error": " ".join(details) or "Finalized dates require both departure_date and return_date.",
            "response_constraints": base_constraints
        }))
        return

    print(json.dumps({
        "ok": True,
        "date_status": "dates_complete",
        "missing_fields": [],
        "destination_provided": is_nonempty_string(payload.get("destination")),
        "response_constraints": base_constraints + [
            "Dates are internally consistent, but the helper does not determine whether or how they must be supplied to a bank workflow."
        ]
    }))


if __name__ == "__main__":
    main()
