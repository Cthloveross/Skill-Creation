#!/usr/bin/env python3
"""Validate the structural output contract for a generated itinerary.
stdin: {"path": "..."}; stdout: {"ok": true} or {"ok": false, "error": "..."}.
"""
import json
import sys
from pathlib import Path


def validate(obj):
    if not isinstance(obj, dict) or set(obj) != {"plan", "tool_called"}:
        raise ValueError("artifact must contain exactly plan and tool_called")
    if not isinstance(obj["tool_called"], list) or not all(isinstance(x, str) for x in obj["tool_called"]):
        raise ValueError("tool_called must be an array of strings")
    plan = obj["plan"]
    if not isinstance(plan, list) or len(plan) != 7:
        raise ValueError("plan must contain exactly seven entries")
    keys = {"day", "current_city", "transportation", "breakfast", "lunch", "dinner", "attraction", "accommodation"}
    for expected_day, item in enumerate(plan, 1):
        if not isinstance(item, dict) or set(item) != keys:
            raise ValueError("day %d keys do not match contract" % expected_day)
        if type(item["day"]) is not int or item["day"] != expected_day:
            raise ValueError("invalid day number at position %d" % expected_day)
        for key in keys - {"day"}:
            if not isinstance(item[key], str):
                raise ValueError("day %d %s is not a string" % (expected_day, key))
        if not item["attraction"].endswith(";"):
            raise ValueError("day %d attraction must end with semicolon" % expected_day)
        if "flight" in item["transportation"].lower():
            raise ValueError("day %d uses prohibited flight transport" % expected_day)


def main():
    try:
        request = json.load(sys.stdin)
        path = Path(request["path"])
        with path.open("r", encoding="utf-8") as fh:
            obj = json.load(fh)
        validate(obj)
        print(json.dumps({"ok": True, "path": str(path)}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
