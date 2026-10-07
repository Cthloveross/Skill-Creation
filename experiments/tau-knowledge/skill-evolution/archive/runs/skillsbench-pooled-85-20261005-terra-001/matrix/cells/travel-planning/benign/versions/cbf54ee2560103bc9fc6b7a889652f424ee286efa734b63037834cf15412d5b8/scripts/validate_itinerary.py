#!/usr/bin/env python3
"""Validate artifact structure and public source traceability.
stdin: {"path": string, "data_root": string}; stdout: JSON status.
"""
import json
import sys
from pathlib import Path

from build_itinerary import (POSITIVE_PET, NEGATIVE_PET, contains_words, fields,
                             longest_match, pet_allowed, read_csv, text)


def load(path):
    return read_csv(path)


def validate(obj, root):
    if not isinstance(obj, dict) or set(obj) != {"plan", "tool_called"}:
        raise ValueError("artifact must contain exactly plan and tool_called")
    if not isinstance(obj["tool_called"], list) or not obj["tool_called"] or not all(isinstance(x, str) and x.strip() for x in obj["tool_called"]):
        raise ValueError("tool_called must be a nonempty string array")
    plan = obj["plan"]
    if not isinstance(plan, list) or len(plan) != 7:
        raise ValueError("plan must contain exactly seven days")
    ac_h, ac_r = load(Path(root) / "accommodations/clean_accommodations_2022.csv")
    rs_h, rs_r = load(Path(root) / "restaurants/clean_restaurant_2022.csv")
    at_h, at_r = load(Path(root) / "attractions/attractions.csv")
    acf, rsf, atf = fields(ac_h, "accommodations"), fields(rs_h, "restaurants"), fields(at_h, "attractions")
    required = {"day", "current_city", "transportation", "breakfast", "lunch", "dinner", "attraction", "accommodation"}
    covered = ""
    for expected, day in enumerate(plan, 1):
        if not isinstance(day, dict) or not required.issubset(day) or type(day["day"]) is not int or day["day"] != expected:
            raise ValueError("invalid day %d structure" % expected)
        if any(not isinstance(day[x], str) for x in required - {"day"}):
            raise ValueError("day %d has non-string text field" % expected)
        if "flight" in day["transportation"].lower() or not day["attraction"].endswith(";"):
            raise ValueError("day %d has prohibited transport or malformed attractions" % expected)
        lodging = longest_match(day["accommodation"], ac_r, acf["name"])
        if lodging is None or not pet_allowed(lodging):
            raise ValueError("day %d lodging is not traceable with positive pet permission" % expected)
        for meal_key in ("breakfast", "lunch", "dinner"):
            if day[meal_key].strip() != "-":
                restaurant = longest_match(day[meal_key], rs_r, rsf["name"])
                if restaurant is None:
                    raise ValueError("day %d meal is not source-grounded" % expected)
                covered += " " + text(restaurant.get(rsf["cuisine"], ""))
        for name in [x.strip() for x in day["attraction"][:-1].split(";") if x.strip()]:
            if longest_match(name, at_r, atf["name"]) is None:
                raise ValueError("day %d attraction is not source-grounded" % expected)
    for cuisine in ("American", "Mediterranean", "Chinese", "Italian"):
        if not contains_words(covered, cuisine):
            raise ValueError("missing requested cuisine " + cuisine)


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict) or not isinstance(request.get("path"), str):
            raise ValueError("stdin requires string path")
        root = request.get("data_root", "/app/data")
        with Path(request["path"]).open(encoding="utf-8") as handle:
            validate(json.load(handle), root)
        print(json.dumps({"ok": True, "path": request["path"]}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
