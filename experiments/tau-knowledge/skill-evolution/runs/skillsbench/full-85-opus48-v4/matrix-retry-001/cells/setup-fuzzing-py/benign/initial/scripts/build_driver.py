#!/usr/bin/env python3
"""Analyze one library and write its notes + fuzz driver (no venv/run).

stdin : {"lib": "/app/<lib>"}
stdout: {"lib","import_name","pkg_parent","module","func","candidates":[...],
         "notes_path","driver_path"}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuzz_helpers as H


def build_one(libdir):
    libdir = os.path.abspath(libdir)
    import_name, pkg_parent, pkg_dir = H.detect_package(libdir)
    candidates = H.find_candidates(import_name, pkg_parent, pkg_dir)
    chosen = candidates[0] if candidates else None
    module = chosen["module"] if chosen else import_name
    func = chosen["func"] if chosen else None
    notes = H.render_notes(libdir, import_name, pkg_parent, candidates, chosen)
    notes_path = os.path.join(libdir, "notes_for_testing.txt")
    with open(notes_path, "w", encoding="utf-8") as fh:
        fh.write(notes)
    driver_path = os.path.join(libdir, "fuzz.py")
    if func is not None:
        with open(driver_path, "w", encoding="utf-8") as fh:
            fh.write(H.render_driver(pkg_parent, module, func))
    return {
        "lib": libdir, "import_name": import_name, "pkg_parent": pkg_parent,
        "module": module, "func": func,
        "candidates": candidates[:15],
        "notes_path": notes_path,
        "driver_path": driver_path if func is not None else None,
    }


def main():
    req = json.load(sys.stdin)
    out = build_one(req["lib"])
    json.dump(out, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
