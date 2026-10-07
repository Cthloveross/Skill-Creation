#!/usr/bin/env python3
"""Discover library projects.

stdin : {"root": "/app"}
stdout: {"libraries": ["/app/<lib>", ...]}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuzz_helpers as H


def main():
    try:
        req = json.load(sys.stdin)
    except Exception:
        req = {}
    root = os.path.abspath(req.get("root", "/app"))
    libs = H.discover_libraries(root)
    json.dump({"libraries": libs}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
