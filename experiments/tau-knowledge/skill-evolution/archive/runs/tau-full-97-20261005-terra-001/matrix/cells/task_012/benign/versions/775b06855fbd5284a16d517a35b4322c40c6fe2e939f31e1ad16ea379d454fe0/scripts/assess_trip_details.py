#!/usr/bin/env python3
"""Assess itinerary-date completeness without deciding bank policy.

Read one JSON object from stdin:
{
  "destination": "optional string",
  "dates_confirmed": true | false,
  "departure_date": "YYYY-MM-DD, required if dates_confirmed is true",
  "return_date": "YYYY-MM-DD, required if dates_confirmed is true",
  "trip_timing": "optional free-text description"
}

Write one JSON object to stdout. Successful output has date_status of
"dates_not_final" or "dates_complete". Invalid finalized details produce
"invalid_date_details" and ok false.

This program deliberately does not convert relative timing phrases, decide whether
travel-notification dates are required, determine eligibility, or call banking tools.
"""

import datetime as dt
import json
import sys


def nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def parse_iso_date(value):
    if not nonempty_string(value):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def emit(value):
    print(json.dumps(value, separators=(",", ":"), sort_keys=True))


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        emit({"ok": False, "error": "Input must be a JSON object."})
        return

    if not isinstance(payload, dict):
        emit({"ok": False, "error": "Input must be a JSON object."})
        return

    confirmed = payload.get("dates_confirmed")
    if not isinstance(confirmed, bool):
        emit({
            "ok": False,
            "error": "dates_confirmed must be a boolean.",
            "response_constraints": [
                "Do not infer a finalized itinerary from a relative timing phrase."
            ],
        })
        return

    base_constraints = [
        "Do not state that exact dates are optional or mandatory for a travel notification unless documented account policy establishes that.",
        "Do not claim that a notification was submitted or that travel transactions will be approved.",
    ]

    if not confirmed:
        emit({
            "ok": True,
            "date_status": "dates_not_final",
            "missing_fields": ["departure_date", "return_date"],
            "destination_provided": nonempty_string(payload.get("destination")),
            "response_constraints": base_constraints + [
                "Explain that supplied material does not resolve whether a notification can proceed before dates are finalized."
            ],
        })
        return

    missing = [
        field for field in ("departure_date", "return_date")
        if not nonempty_string(payload.get(field))
    ]
    departure = parse_iso_date(payload.get("departure_date"))
    returning = parse_iso_date(payload.get("return_date"))

    invalid_format = not missing and (departure is None or returning is None)
    reverse_range = departure is not None and returning is not None and returning < departure
    if missing or invalid_format or reverse_range:
        details = []
        if invalid_format:
            details.append("Dates must use YYYY-MM-DD.")
        if reverse_range:
            details.append("return_date cannot be before departure_date.")
        if not details:
            details.append("Finalized dates require both departure_date and return_date.")
        emit({
            "ok": False,
            "date_status": "invalid_date_details",
            "missing_fields": missing,
            "error": " ".join(details),
            "response_constraints": base_constraints,
        })
        return

    emit({
        "ok": True,
        "date_status": "dates_complete",
        "missing_fields": [],
        "destination_provided": nonempty_string(payload.get("destination")),
        "response_constraints": base_constraints + [
            "Internally consistent dates do not establish whether or how they must be supplied to a bank workflow."
        ],
    })


if __name__ == "__main__":
    main()
