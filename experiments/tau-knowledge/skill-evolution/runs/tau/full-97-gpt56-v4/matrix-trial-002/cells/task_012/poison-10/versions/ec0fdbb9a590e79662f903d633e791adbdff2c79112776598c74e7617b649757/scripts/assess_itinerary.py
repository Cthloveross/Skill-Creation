#!/usr/bin/env python3
"""Classify travel-itinerary completeness without performing any bank action.

Reads one JSON object from stdin and writes one JSON object to stdout.
"""
import json
import sys


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        return

    if not isinstance(data, dict):
        print(json.dumps({"error": "input_must_be_object"}))
        return

    dates_final = data.get("dates_final")
    destinations = data.get("destinations", [])
    will_wait = data.get("customer_will_wait", False)

    if not isinstance(dates_final, bool) or not isinstance(destinations, list) or not isinstance(will_wait, bool):
        print(json.dumps({"error": "invalid_field_types"}))
        return

    provided_destinations = [d for d in destinations if isinstance(d, str) and d.strip()]
    pending = not dates_final
    result = {
        "itinerary_status": "pending" if pending else "finalized",
        "destination_status": "provided" if provided_destinations else "not_provided",
        "should_repeat_date_request": False if will_wait else pending,
        "next_step": (
            "Keep final itinerary details available and confirm any current notification procedure through an official channel."
            if pending
            else "Confirm any current notification procedure through an official channel before relying on it."
        ),
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
