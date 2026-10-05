#!/usr/bin/env python3
"""Public-task entrypoint. stdin is a JSON object of optional overrides."""
import json
import sys
from pathlib import Path

from build_itinerary import build
from validate_itinerary import validate

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
}


def main():
    try:
        overrides = json.load(sys.stdin)
        if not isinstance(overrides, dict):
            raise ValueError("stdin must be a JSON object")
        config = dict(DEFAULTS)
        config.update(overrides)
        result = build(config)
        with Path(config["output_path"]).open(encoding="utf-8") as handle:
            artifact = json.load(handle)
        validate(artifact, config["data_root"], config["origin"], config["target_state"])
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
