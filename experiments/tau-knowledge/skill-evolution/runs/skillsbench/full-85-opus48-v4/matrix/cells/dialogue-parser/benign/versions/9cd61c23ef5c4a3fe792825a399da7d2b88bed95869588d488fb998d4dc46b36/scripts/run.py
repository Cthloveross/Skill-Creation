#!/usr/bin/env python3
"""Optional convenience wrapper around solution.py.

This never reads stdin (so it can never block an automated executor). It simply
delegates to solution.main(), which installs the deliverable module to
/app/solution.py and writes /app/dialogue.json and /app/dialogue.dot.

Usage (all optional, positional, same as solution.py):
  python run.py [script_path] [out_json] [out_dot]
Defaults: /app/script.txt /app/dialogue.json /app/dialogue.dot

Prefer running solution.py directly; this wrapper exists only for callers that
expect a `run.py` entrypoint.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import solution  # noqa: E402


if __name__ == "__main__":
    sys.exit(solution.main(sys.argv))
