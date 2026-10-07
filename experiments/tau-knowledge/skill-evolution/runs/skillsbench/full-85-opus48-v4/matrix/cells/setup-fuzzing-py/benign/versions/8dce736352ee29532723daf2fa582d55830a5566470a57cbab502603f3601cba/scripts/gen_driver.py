#!/usr/bin/env python3
"""Generate fuzz.py for one library from analyze.py's cached targets (or a
fresh analysis if the cache is missing).

stdin JSON: {"library": "/app/LIB"}
stdout JSON: {"library", "fuzz_path", "n_targets"}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuzzlib


def main():
    req = json.load(sys.stdin)
    lib = req["library"]
    cache = os.path.join(lib, ".fuzz_targets.json")
    if os.path.exists(cache):
        data = json.load(open(cache, "r", encoding="utf-8"))
        pkg = data.get("package")
        cands = data.get("candidates", [])
    else:
        pkg = fuzzlib.find_package(lib)
        cands = fuzzlib.find_candidates(lib, pkg) if pkg else []
    if pkg is None:
        print(json.dumps({"library": lib, "fuzz_path": None,
                          "error": "no package"}))
        return
    path = fuzzlib.generate_driver(lib, pkg, cands)
    print(json.dumps({"library": lib, "fuzz_path": path,
                      "n_targets": len(cands)}))


if __name__ == "__main__":
    main()
