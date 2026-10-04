#!/usr/bin/env python3
"""Entrypoint: calculate and write the required mass_report.json.

Reads a JSON object from stdin and emits a JSON object on stdout.
"""

from __future__ import annotations

import json
import os
import sys
import traceback

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from stl_mass_core import calculate_and_write  # noqa: E402


def main() -> int:
    try:
        raw = sys.stdin.read().strip()
        config = json.loads(raw) if raw else {}
        if not isinstance(config, dict):
            raise ValueError("stdin JSON must be an object")
        result = calculate_and_write(config)
        print(json.dumps({"status": "ok", **result}, indent=2, sort_keys=False))
        return 0
    except Exception as exc:  # pragma: no cover - entrypoint safety
        payload = {
            "status": "error",
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }
        if os.environ.get("SKILL_DEBUG_TRACEBACK"):
            payload["traceback"] = traceback.format_exc()
        print(json.dumps(payload, indent=2, sort_keys=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
