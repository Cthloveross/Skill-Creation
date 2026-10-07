#!/usr/bin/env python3
"""Locate the editable failed BugSwarm repository.

Input  (stdin JSON): {"base": "/home/github/build/failed"}  (base optional)
Output (stdout JSON): {
  "base": str,
  "candidates": [ {"path","repo","id","markers","git","workflows"} ],
  "path": str|null,          # chosen path when exactly one candidate
  "workflow_files": [str],   # .github/workflows/* for the chosen path
  "note": str
}
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DEFAULT_BASE, emit, find_repo, read_input  # noqa: E402


def main():
    inp = read_input()
    base = inp.get("base", DEFAULT_BASE)
    cands = find_repo(base)
    chosen = cands[0]["path"] if len(cands) == 1 else None
    wf = []
    if chosen:
        wdir = os.path.join(chosen, ".github", "workflows")
        if os.path.isdir(wdir):
            wf = [os.path.join(wdir, f) for f in sorted(os.listdir(wdir))]
    if not cands:
        note = "no candidate found; inspect %s manually" % base
    elif chosen:
        note = "single candidate selected"
    else:
        note = "multiple candidates; choose one and pass it as repo"
    emit(
        {
            "base": base,
            "candidates": cands,
            "path": chosen,
            "workflow_files": wf,
            "note": note,
        }
    )


if __name__ == "__main__":
    main()
