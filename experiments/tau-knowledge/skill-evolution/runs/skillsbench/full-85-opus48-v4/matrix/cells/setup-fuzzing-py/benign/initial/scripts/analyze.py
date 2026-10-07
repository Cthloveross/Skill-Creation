#!/usr/bin/env python3
"""Analyze one library: locate package, rank parser-like functions, write
notes_for_testing.txt, and cache the chosen targets for gen_driver.py.

stdin JSON: {"library": "/app/LIB", "limit": 5}
stdout JSON: {"library", "package", "candidates": [...], "notes_path"}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuzzlib


def analyze(libdir, limit=5):
    pkg = fuzzlib.find_package(libdir)
    if pkg is None:
        return {"library": libdir, "package": None, "candidates": [],
                "notes_path": None, "error": "no importable package found"}
    cands = fuzzlib.find_candidates(libdir, pkg, limit=limit)
    notes = fuzzlib.write_notes(libdir, pkg, cands)
    # cache for gen_driver
    cache = os.path.join(libdir, ".fuzz_targets.json")
    with open(cache, "w", encoding="utf-8") as fh:
        json.dump({"package": pkg, "candidates": cands}, fh)
    return {"library": libdir, "package": pkg, "candidates": cands,
            "notes_path": notes}


def main():
    req = json.load(sys.stdin)
    lib = req["library"]
    limit = int(req.get("limit", 5))
    print(json.dumps(analyze(lib, limit)))


if __name__ == "__main__":
    main()
