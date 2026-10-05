#!/usr/bin/env python3
"""Validate a serialized itinerary against the mounted public data.

stdin: {"path": string, "data_root": string}
stdout: {"ok": true, "path": string} or {"ok": false, "error": string}
"""
import json
import re
import sys
from pathlib import Path

from build_itinerary import (best_named_row, clean, load_sources, ohio_city_displays,
                             pet_allowed, words_in)


def validate(artifact, root, origin="Minneapolis", state="Ohio"):
    if not isinstance(artifact, dict) or not isinstance(artifact.get("plan"), list):
        raise ValueError("artifact must be an object with a plan array")
    if len(artifact["plan"]) != 7:
        raise ValueError("plan must contain exactly seven day objects")
    tools = artifact.get("tool_called")
    if not isinstance(tools, list) or not tools or not all(isinstance(x, str) and x.strip() for x in tools):
        raise ValueError("tool_called must be a nonempty string array")

    headers, accommodations, restaurants, attractions, ac, rc, tc = load_sources(root)
    fields = {"day", "current_city", "transportation", "breakfast", "lunch", "dinner", "attraction", "accommodation"}
    route_text, cuisines = "", ""
    for expected, day in enumerate(artifact["plan"], 1):
        if not isinstance(day, dict) or not fields.issubset(day):
            raise ValueError("day %d lacks required fields" % expected)
        if type(day["day"]) is not int or day["day"] != expected:
            raise ValueError("days must be ordered integers 1 through 7")
        if any(not isinstance(day[f], str) for f in fields - {"day"}):
            raise ValueError("day %d has a non-string text field" % expected)
        if not all(day[f].strip() for f in ("current_city", "transportation", "accommodation")):
            raise ValueError("day %d has blank travel or lodging data" % expected)
        if re.search(r"\b(flight|flights|fly|flying|airplane|air travel)\b", day["transportation"], re.I):
            raise ValueError("air travel is prohibited")
        text = day["attraction"].strip()
        if not text.endswith(";"):
            raise ValueError("day %d attraction must end with semicolon" % expected)
        listed = [x.strip() for x in text[:-1].split(";") if x.strip()]
        if not listed or any(best_named_row(x, attractions, tc["name"]) is None for x in listed):
            raise ValueError("day %d has an untraceable attraction" % expected)
        lodging = best_named_row(day["accommodation"], accommodations, ac["name"])
        if lodging is None or not pet_allowed(lodging, headers):
            raise ValueError("day %d lodging lacks explicit public-record pet permission" % expected)
        for field in ("breakfast", "lunch", "dinner"):
            if day[field].strip() != "-":
                restaurant = best_named_row(day[field], restaurants, rc["name"])
                if restaurant is None:
                    raise ValueError("day %d %s is not source-grounded" % (expected, field))
                cuisines += " " + clean(restaurant.get(rc["cuisine"], ""))
        route_text += " " + " ".join(str(x) for x in day.values())

    for wanted in ("American", "Mediterranean", "Chinese", "Italian"):
        if not re.search(r"\b" + re.escape(wanted) + r"\b", cuisines, re.I):
            raise ValueError("requested cuisine missing: " + wanted)
    if not words_in(route_text, origin):
        raise ValueError("Minneapolis departure is absent")
    values = [r.get(ac["city"], "") for r in accommodations] + [r.get(rc["city"], "") for r in restaurants] + [r.get(tc["city"], "") for r in attractions]
    ohio = ohio_city_displays(root, values, state)
    if sum(words_in(route_text, city) for city in ohio) < 3:
        raise ValueError("fewer than three source-supported Ohio cities are named")


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict) or not isinstance(request.get("path"), str):
            raise ValueError("stdin requires an object with string path")
        with Path(request["path"]).open(encoding="utf-8") as f:
            artifact = json.load(f)
        validate(artifact, request.get("data_root", "/app/data"))
        print(json.dumps({"ok": True, "path": request["path"]}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
