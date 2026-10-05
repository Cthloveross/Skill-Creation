#!/usr/bin/env python3
"""Perform structural validation that one active rule has a requested SID.

Input: {"rules_path": string, "sid": positive integer}
Output: {"ok": bool, "target_rule_count": integer, "errors": [string]}
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


def valid_sid(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def main() -> int:
    try:
        spec = json.load(sys.stdin)
        if not isinstance(spec, dict):
            raise ValueError("input must be a JSON object")
        path_value = spec.get("rules_path")
        sid = spec.get("sid")
        if not isinstance(path_value, str) or not path_value:
            raise ValueError("rules_path must be a nonempty string")
        if not valid_sid(sid):
            raise ValueError("sid must be a positive integer")
        path = Path(path_value)
        if not path.is_file():
            raise ValueError("rules_path must name an existing regular file")
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        print(json.dumps({"ok": False, "target_rule_count": 0, "errors": [str(exc)]}, sort_keys=True))
        return 2

    matcher = re.compile(r"\bsid\s*:\s*" + re.escape(str(sid)) + r"\s*;", re.IGNORECASE)
    active = [line for line in text.splitlines()
              if matcher.search(line) and not line.lstrip().startswith("#")]
    errors: List[str] = []
    if len(active) != 1:
        errors.append("expected exactly one active rule with the requested sid")
    elif not active[0].lstrip().lower().startswith("alert "):
        errors.append("the requested sid is not on an alert rule")
    elif active[0].count("(") != active[0].count(")"):
        errors.append("the target rule has unbalanced parentheses")

    result = {"ok": not errors, "target_rule_count": len(active), "errors": errors}
    print(json.dumps(result, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
