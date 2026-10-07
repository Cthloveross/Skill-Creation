#!/usr/bin/env python3
"""Execute the fixed public travel-planning request.

stdin: optional JSON object of documented builder overrides.
stdout: builder status JSON.
"""
import json
import sys

from build_itinerary import build

DEFAULTS = {
    "data_root": "/app/data",
    "output_path": "/app/output/itinerary.json",
    "origin": "Minneapolis",
    "target_state": "Ohio",
    "start_date": "2022-03-17",
    "end_date": "2022-03-23",
    "party_size": 2,
    "budget": 5100,
    "cuisines": ["American", "Mediterranean", "Chinese", "Italian"],
    "days": 7,
    "city_count": 3,
    "pet_required": True,
}


def main():
    try:
        supplied = json.load(sys.stdin)
        if not isinstance(supplied, dict):
            raise ValueError("stdin must contain a JSON object")
        request = dict(DEFAULTS)
        request.update(supplied)
        print(json.dumps(build(request), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
