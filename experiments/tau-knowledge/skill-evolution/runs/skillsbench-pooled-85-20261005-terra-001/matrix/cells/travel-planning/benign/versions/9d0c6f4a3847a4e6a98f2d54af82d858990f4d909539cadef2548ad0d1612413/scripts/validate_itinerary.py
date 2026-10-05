#!/usr/bin/env python3
"""Validate an itinerary artifact against the mounted public travel data.

stdin: {"path": string, "data_root": string}
stdout: {"ok":true,"path":string} or {"ok":false,"error":string}
"""
import json
import re
import sys
from pathlib import Path

from build_itinerary import clean, load, matched_row, ohio_cities, pet_allowed, words_in


def validate(artifact, root, origin="Minneapolis", state="Ohio"):
    if not isinstance(artifact, dict) or not isinstance(artifact.get("plan"), list):
        raise ValueError("artifact must be an object with a plan array")
    if len(artifact["plan"]) != 7:
        raise ValueError("plan must contain exactly seven day objects")
    tools = artifact.get("tool_called")
    if not isinstance(tools, list) or not tools or not all(isinstance(x, str) and x.strip() for x in tools):
        raise ValueError("tool_called must be a nonempty string array")

    headers, accommodations, restaurants, attractions, ac, rc, tc = load(root)
    required = {"day", "current_city", "transportation", "breakfast", "lunch", "dinner", "attraction", "accommodation"}
    cuisine_text, route_text = "", ""
    for expected, entry in enumerate(artifact["plan"], 1):
        if not isinstance(entry, dict) or not required.issubset(entry):
            raise ValueError("day %d lacks required fields" % expected)
        if type(entry["day"]) is not int or entry["day"] != expected:
            raise ValueError("days must be ordered integers from 1 through 7")
        if any(not isinstance(entry[key], str) for key in required - {"day"}):
            raise ValueError("day %d has a non-string field" % expected)
        if any(not entry[key].strip() for key in ("current_city", "transportation", "accommodation")):
            raise ValueError("day %d has blank route or lodging text" % expected)
        if re.search(r"\b(flight|flights|fly|flying|airplane|air travel)\b", entry["transportation"], re.I):
            raise ValueError("air travel is prohibited")

        text = entry["attraction"].strip()
        listed = [part.strip() for part in text[:-1].split(";") if part.strip()] if text.endswith(";") else []
        if not listed:
            raise ValueError("day %d attraction must be a nonempty semicolon-terminated list" % expected)
        if any(matched_row(name, attractions, tc["name"]) is None for name in listed):
            raise ValueError("day %d has an untraceable attraction" % expected)

        lodging = matched_row(entry["accommodation"], accommodations, ac["name"])
        if lodging is None or not pet_allowed(lodging, headers):
            raise ValueError("day %d lodging lacks explicit public-record pet permission" % expected)
        for field in ("breakfast", "lunch", "dinner"):
            meal = entry[field].strip()
            if meal == "-":
                continue
            restaurant = matched_row(meal, restaurants, rc["name"])
            if restaurant is None:
                raise ValueError("day %d %s is not source-grounded" % (expected, field))
            cuisine_text += " " + clean(restaurant.get(rc["cuisine"], ""))
        route_text += " " + " ".join(str(value) for value in entry.values())

    for cuisine in ("American", "Mediterranean", "Chinese", "Italian"):
        if not re.search(r"\b" + re.escape(cuisine) + r"\b", cuisine_text, re.I):
            raise ValueError("requested cuisine missing: " + cuisine)
    if not words_in(route_text, origin):
        raise ValueError("requested Minneapolis departure is absent")
    city_values = [row.get(ac["city"], "") for row in accommodations]
    city_values += [row.get(rc["city"], "") for row in restaurants]
    city_values += [row.get(tc["city"], "") for row in attractions]
    cities = ohio_cities(root, city_values, state)
    if sum(words_in(route_text, city) for city in cities) < 3:
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
