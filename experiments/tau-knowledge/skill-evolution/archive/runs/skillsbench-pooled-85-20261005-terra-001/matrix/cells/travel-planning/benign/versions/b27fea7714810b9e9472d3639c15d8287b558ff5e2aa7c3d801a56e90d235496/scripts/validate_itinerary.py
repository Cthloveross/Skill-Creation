#!/usr/bin/env python3
"""Validate itinerary JSON against mounted public data.

stdin: {"path": string, "data_root": string}
stdout: {"ok": bool, ...}
"""
import json
import re
import sys
from pathlib import Path

from build_itinerary import (best_named_row, clean, load_sources, ohio_displays,
                             pet_allowed, words_in)


def validate(obj, root, origin="Minneapolis", state="Ohio"):
    if not isinstance(obj, dict) or not isinstance(obj.get("plan"), list) or len(obj["plan"]) != 7:
        raise ValueError("artifact requires a seven-item plan array")
    tools = obj.get("tool_called")
    if not isinstance(tools, list) or not tools or not all(isinstance(x, str) and x.strip() for x in tools):
        raise ValueError("tool_called must be a nonempty string array")

    headers, accommodations, restaurants, attractions, ac, rc, tc = load_sources(root)
    required = {"day", "current_city", "transportation", "breakfast", "lunch", "dinner", "attraction", "accommodation"}
    cuisine_text, route_text = "", ""
    for expected, day in enumerate(obj["plan"], 1):
        if not isinstance(day, dict) or not required.issubset(day):
            raise ValueError("invalid day structure %d" % expected)
        if type(day["day"]) is not int or day["day"] != expected:
            raise ValueError("days must be sequential integers")
        if any(not isinstance(day[field], str) for field in required - {"day"}):
            raise ValueError("day %d has a non-string field" % expected)
        if not day["attraction"].strip().endswith(";"):
            raise ValueError("day %d attraction lacks final semicolon" % expected)
        if re.search(r"\b(flight|flights|fly|flying|airplane|air travel)\b", day["transportation"], re.I):
            raise ValueError("air transport is prohibited")

        lodging = best_named_row(day["accommodation"], accommodations, ac["name"])
        if lodging is None or not pet_allowed(lodging, headers):
            raise ValueError("day %d accommodation lacks explicit database pet permission" % expected)
        for field in ("breakfast", "lunch", "dinner"):
            if day[field].strip() != "-":
                restaurant = best_named_row(day[field], restaurants, rc["name"])
                if restaurant is None:
                    raise ValueError("day %d %s is not source-grounded" % (expected, field))
                cuisine_text += " " + clean(restaurant.get(rc["cuisine"], ""))
        names = [part.strip() for part in day["attraction"].strip()[:-1].split(";") if part.strip()]
        if not names or any(best_named_row(name, attractions, tc["name"]) is None for name in names):
            raise ValueError("day %d attraction is not source-grounded" % expected)
        route_text += " " + " ".join(str(value) for value in day.values())

    for cuisine in ("American", "Mediterranean", "Chinese", "Italian"):
        if not re.search(r"\b" + re.escape(cuisine) + r"\b", cuisine_text, re.I):
            raise ValueError("missing cuisine: " + cuisine)
    if not words_in(route_text, origin):
        raise ValueError("origin is absent")
    cities = [row.get(ac["city"], "") for row in accommodations]
    cities += [row.get(rc["city"], "") for row in restaurants]
    cities += [row.get(tc["city"], "") for row in attractions]
    ohio = ohio_displays(root, cities, state)
    if len([key for key in ohio if words_in(route_text, key)]) < 3:
        raise ValueError("fewer than three supported Ohio cities")


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict) or not isinstance(request.get("path"), str):
            raise ValueError("stdin requires a string path")
        with Path(request["path"]).open("r", encoding="utf-8") as handle:
            artifact = json.load(handle)
        validate(artifact, request.get("data_root", "/app/data"))
        print(json.dumps({"ok": True, "path": request["path"]}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
