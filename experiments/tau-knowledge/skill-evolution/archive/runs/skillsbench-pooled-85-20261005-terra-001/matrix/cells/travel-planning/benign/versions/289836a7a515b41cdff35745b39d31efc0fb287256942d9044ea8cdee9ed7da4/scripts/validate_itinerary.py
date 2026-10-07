#!/usr/bin/env python3
"""Validate a serialized itinerary against mounted public travel data.

stdin: {"path": string, "data_root": string}
stdout: {"ok": true, "path": string} or {"ok": false, "error": string}
"""
import json
import re
import sys
from pathlib import Path

from build_itinerary import (
    best_named_row,
    clean,
    load_sources,
    ohio_city_displays,
    pet_allowed,
    words_in,
)


def validate(artifact, root, origin="Minneapolis", state="Ohio"):
    if not isinstance(artifact, dict) or not isinstance(artifact.get("plan"), list):
        raise ValueError("artifact must be a JSON object with a plan array")
    if len(artifact["plan"]) != 7:
        raise ValueError("plan must contain exactly seven day objects")
    tools = artifact.get("tool_called")
    if not isinstance(tools, list) or not tools or not all(isinstance(x, str) and x.strip() for x in tools):
        raise ValueError("tool_called must be a nonempty string array")

    headers, accommodations, restaurants, attractions, ac, rc, tc = load_sources(root)
    required_fields = {
        "day", "current_city", "transportation", "breakfast", "lunch", "dinner", "attraction", "accommodation"
    }
    observed_cuisines = ""
    route_text = ""

    for expected_day, day in enumerate(artifact["plan"], 1):
        if not isinstance(day, dict) or not required_fields.issubset(day):
            raise ValueError("day %d lacks required fields" % expected_day)
        if type(day["day"]) is not int or day["day"] != expected_day:
            raise ValueError("days must be ordered integers from 1 through 7")
        if any(not isinstance(day[field], str) for field in required_fields - {"day"}):
            raise ValueError("day %d has a non-string text field" % expected_day)
        if any(not day[field].strip() for field in ("current_city", "transportation", "accommodation")):
            raise ValueError("day %d has blank route or lodging data" % expected_day)
        if re.search(r"\b(flight|flights|fly|flying|airplane|air travel)\b", day["transportation"], re.I):
            raise ValueError("air travel is prohibited")

        attraction_text = day["attraction"].strip()
        if not attraction_text.endswith(";"):
            raise ValueError("day %d attraction must end with a semicolon" % expected_day)
        attraction_names = [part.strip() for part in attraction_text[:-1].split(";") if part.strip()]
        if not attraction_names:
            raise ValueError("day %d has no attraction" % expected_day)
        for name in attraction_names:
            if best_named_row(name, attractions, tc["name"]) is None:
                raise ValueError("day %d has an untraceable attraction" % expected_day)

        # Inspect policy evidence from the exact row that the public name matcher resolves.
        lodging = best_named_row(day["accommodation"], accommodations, ac["name"])
        if lodging is None or not pet_allowed(lodging, headers):
            raise ValueError("day %d lodging lacks explicit public-record pet permission" % expected_day)

        for field in ("breakfast", "lunch", "dinner"):
            meal = day[field].strip()
            if meal == "-":
                continue
            restaurant = best_named_row(meal, restaurants, rc["name"])
            if restaurant is None:
                raise ValueError("day %d %s is not source-grounded" % (expected_day, field))
            observed_cuisines += " " + clean(restaurant.get(rc["cuisine"], ""))
        route_text += " " + " ".join(str(value) for value in day.values())

    for wanted in ("American", "Mediterranean", "Chinese", "Italian"):
        if not re.search(r"\b" + re.escape(wanted) + r"\b", observed_cuisines, re.I):
            raise ValueError("requested cuisine missing: " + wanted)
    if not words_in(route_text, origin):
        raise ValueError("requested Minneapolis departure is absent")

    values = [row.get(ac["city"], "") for row in accommodations]
    values += [row.get(rc["city"], "") for row in restaurants]
    values += [row.get(tc["city"], "") for row in attractions]
    ohio = ohio_city_displays(root, values, state)
    visited = sum(words_in(route_text, city) for city in ohio)
    if visited < 3:
        raise ValueError("fewer than three source-supported target-state cities are named")


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict) or not isinstance(request.get("path"), str):
            raise ValueError("stdin requires an object with string path")
        with Path(request["path"]).open(encoding="utf-8") as handle:
            artifact = json.load(handle)
        validate(artifact, request.get("data_root", "/app/data"))
        print(json.dumps({"ok": True, "path": request["path"]}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
