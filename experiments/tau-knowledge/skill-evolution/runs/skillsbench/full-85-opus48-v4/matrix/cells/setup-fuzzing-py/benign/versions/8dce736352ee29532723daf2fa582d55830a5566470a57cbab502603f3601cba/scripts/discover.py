#!/usr/bin/env python3
"""Discover library projects and write the listing file.

stdin JSON: {"root": "/app", "listing": "/app/libraries.txt"}
  root     optional, default "/app"
  listing  optional, default <root>/libraries.txt
stdout JSON: {"libraries": [abs paths...], "listing": path, "count": n}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuzzlib


def main():
    try:
        req = json.load(sys.stdin)
    except Exception:
        req = {}
    root = req.get("root") or "/app"
    listing = req.get("listing") or os.path.join(root, "libraries.txt")
    libs = fuzzlib.discover_libraries(root)
    with open(listing, "w", encoding="utf-8") as fh:
        fh.write("\n".join(libs) + ("\n" if libs else ""))
    # verify each entry resolves
    resolved = [p for p in libs if os.path.isdir(p)]
    print(json.dumps({
        "libraries": libs,
        "listing": listing,
        "count": len(libs),
        "all_resolve": resolved == libs,
    }))


if __name__ == "__main__":
    main()
