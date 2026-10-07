#!/usr/bin/env python3
"""Validate the structural contract of a display-formula Markdown file.

Read JSON from stdin and emit one JSON report.  This validator deliberately
checks only output-file invariants; visual correspondence and whether a
correction is justified remain PDF-review decisions.

Input: {"output_path": "/path/to/file"}
Output: {"valid": bool, "line_count": int, "errors": [string, ...]}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def validate(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("output_path"), str):
        raise ValueError("input must be an object with string output_path")
    path = Path(payload["output_path"])
    if not path.is_file():
        raise ValueError("output_path does not name an existing file")
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    errors: list[str] = []
    if not lines:
        errors.append("file contains no formula lines")
    seen: set[str] = set()
    for number, line in enumerate(lines, 1):
        if not line:
            errors.append("line %d is blank" % number)
            continue
        if line != line.strip():
            errors.append("line %d has leading or trailing whitespace" % number)
        if not (line.startswith("$$") and line.endswith("$$") and len(line) > 4):
            errors.append("line %d is not a nonempty $$...$$ formula" % number)
        if line in seen:
            errors.append("line %d duplicates an earlier formula" % number)
        seen.add(line)
    return {"valid": not errors, "line_count": len(lines), "errors": errors}


def main() -> int:
    try:
        report = validate(json.load(sys.stdin))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "line_count": 0, "errors": [str(exc)]}))
        return 2
    print(json.dumps(report))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
