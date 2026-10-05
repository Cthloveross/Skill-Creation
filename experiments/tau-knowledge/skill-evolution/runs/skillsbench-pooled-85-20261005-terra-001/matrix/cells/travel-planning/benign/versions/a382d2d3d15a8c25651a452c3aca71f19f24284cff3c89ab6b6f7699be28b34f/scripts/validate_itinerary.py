#!/usr/bin/env python3
"""Validate public structural requirements.
stdin: {"path": "..."}; stdout: {"ok": bool, ...}.
"""
import json
import sys
from pathlib import Path


def validate(obj):
    if not isinstance(obj, dict) or set(obj) != {"plan", "tool_called"}:
        raise ValueError("artifact must contain exactly plan and tool_called")
    if not isinstance(obj["tool_called"], list) or not obj["tool_called"] or not all(isinstance(x, str) and x.strip() for x in obj["tool_called"]):
        raise ValueError("tool_called must be a nonempty array of strings")
    plan = obj["plan"]
    if not isinstance(plan, list) or len(plan) != 7:
        raise ValueError("plan must contain exactly seven entries")
    fields = {"day", "current_city", "transportation", "breakfast", "lunch", "dinner", "attraction", "accommodation"}
    for expected, item in enumerate(plan, 1):
        if not isinstance(item, dict) or set(item) != fields:
            raise ValueError("day %d keys do not match contract" % expected)
        if type(item["day"]) is not int or item["day"] != expected:
            raise ValueError("day numbers must be sequential integers")
        for field in fields - {"day"}:
            if not isinstance(item[field], str):
                raise ValueError("day %d field %s must be a string" % (expected, field))
        if not item["attraction"].endswith(";"):
            raise ValueError("day %d attraction must end with semicolon" % expected)
        if "flight" in item["transportation"].lower():
            raise ValueError("day %d uses prohibited flight transport" % expected)


def main():
    try:
        request = json.load(sys.stdin)
        with Path(request["path"]).open("r", encoding="utf-8") as handle:
            validate(json.load(handle))
        print(json.dumps({"ok": True, "path": str(request["path"])}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
