#!/usr/bin/env python3
"""Discover and (optionally) run the BugSwarm failed-build reproduction script.

Input (stdin JSON): {
  "auto": false,            # when true, run the first failed-build script found
  "script": null,           # explicit path to a script to run (overrides auto)
  "timeout": 600,           # seconds
  "log": "/tmp/build_repro.log",
  "tail": 80                # number of trailing log lines to return
}
Output (stdout JSON): {
  "scripts": [str],         # discovered candidate reproduction scripts
  "ran": str|null,          # script actually executed
  "exit_code": int|null,
  "log": str|null,
  "tail": str|null,
  "note": str
}

This script only *runs* the project's own CI entry point. It never edits the
build configuration and never skips tests. A non-zero exit is a failure to
inspect, not evidence of success.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import emit, read_input, run  # noqa: E402

SEARCH_ROOTS = ["/usr/local/bin", "/home/github/build", "/home/github", "/home"]
NAME_HINTS = ("run_failed", "run_build", "build.sh", "run.sh", "reproduce")


def discover():
    found = []
    for root in SEARCH_ROOTS:
        if not os.path.isdir(root):
            continue
        try:
            for name in sorted(os.listdir(root)):
                low = name.lower()
                if low.endswith(".sh") and any(h in low for h in NAME_HINTS):
                    p = os.path.join(root, name)
                    if os.path.isfile(p) and p not in found:
                        found.append(p)
        except OSError:
            continue
    # prefer explicit failed-build scripts first
    found.sort(key=lambda p: (0 if "run_failed" in os.path.basename(p).lower() else 1, p))
    return found


def tail_file(path, n):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
        return "".join(lines[-n:])
    except OSError:
        return None


def main():
    inp = read_input()
    scripts = discover()
    chosen = inp.get("script")
    if not chosen and inp.get("auto") and scripts:
        chosen = scripts[0]
    note = "discovery only"
    exit_code = None
    log = None
    tail = None
    if chosen:
        if not os.path.isfile(chosen):
            emit({"scripts": scripts, "ran": None, "exit_code": None, "log": None,
                  "tail": None, "note": "script not found: %s" % chosen})
            return
        log = inp.get("log", "/tmp/build_repro.log")
        timeout = inp.get("timeout", 600)
        code, out, err = run(["bash", chosen], timeout=timeout)
        try:
            with open(log, "w", encoding="utf-8", errors="replace") as fh:
                fh.write(out)
                fh.write("\n----- STDERR -----\n")
                fh.write(err)
        except OSError:
            pass
        exit_code = code
        tail = tail_file(log, inp.get("tail", 80))
        note = (
            "build reproduced; exit %d (0 = passes). Read the full log for the "
            "first failing traceback." % code
        )
    elif not scripts:
        note = (
            "no reproduction script discovered; run the CI command from "
            "tox.ini / .github/workflows yourself"
        )
    emit(
        {
            "scripts": scripts,
            "ran": chosen,
            "exit_code": exit_code,
            "log": log,
            "tail": tail,
            "note": note,
        }
    )


if __name__ == "__main__":
    main()
