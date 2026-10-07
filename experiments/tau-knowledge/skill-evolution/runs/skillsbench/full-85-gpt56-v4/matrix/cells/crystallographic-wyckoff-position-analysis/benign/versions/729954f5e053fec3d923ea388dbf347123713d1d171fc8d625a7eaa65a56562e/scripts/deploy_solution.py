#!/usr/bin/env python3
"""Copy the reusable analyzer module to a caller-selected task deliverable path.

Reads JSON from stdin: {"target": "/path/to/solution.py"}. Writes a JSON status
object to stdout. The helper does not execute the generated solution.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def main() -> int:
    try:
        raw = sys.stdin.read().strip()
        request = json.loads(raw) if raw else {}
        if not isinstance(request, dict):
            raise ValueError("input must be a JSON object")
        target = Path(request.get("target", "/root/workspace/solution.py"))
        if not str(target):
            raise ValueError("target must be a nonempty path")
        source = Path(__file__).resolve().parents[1] / "references" / "solution.py"
        if not source.is_file():
            raise FileNotFoundError(f"packaged source is unavailable: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        print(json.dumps({"ok": True, "target": str(target)}))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
