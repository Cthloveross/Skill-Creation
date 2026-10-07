#!/usr/bin/env python3
"""End-to-end orchestration for all libraries.

stdin JSON: {"root": "/app", "listing": "/app/libraries.txt",
             "max_total_time": 10}
stdout JSON: {"listing", "libraries", "results": [per-lib summary]}

Runs libraries sequentially to respect memory limits.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fuzzlib


def _call(script, payload):
    p = subprocess.run([sys.executable, os.path.join(HERE, script)],
                       input=json.dumps(payload), capture_output=True,
                       text=True)
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        return {"error": "bad output", "stdout": p.stdout[-500:],
                "stderr": p.stderr[-500:]}


def main():
    try:
        req = json.load(sys.stdin)
    except Exception:
        req = {}
    root = req.get("root") or "/app"
    listing = req.get("listing") or os.path.join(root, "libraries.txt")
    budget = int(req.get("max_total_time", 10))

    disc = _call("discover.py", {"root": root, "listing": listing})
    libs = disc.get("libraries", [])

    results = []
    for lib in libs:
        entry = {"library": lib}
        entry["analyze"] = _call("analyze.py", {"library": lib})
        entry["gen"] = _call("gen_driver.py", {"library": lib})
        entry["setup"] = _call("setup_and_run.py",
                               {"library": lib, "max_total_time": budget})
        entry["files_ok"] = {
            "notes": os.path.exists(os.path.join(lib, "notes_for_testing.txt")),
            "fuzz": os.path.exists(os.path.join(lib, "fuzz.py")),
            "venv": os.path.exists(os.path.join(lib, ".venv", "bin", "python")),
            "log": os.path.exists(os.path.join(lib, "fuzz.log")),
        }
        results.append(entry)

    summary = {
        "listing": listing,
        "libraries": libs,
        "count": len(libs),
        "results": results,
    }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
