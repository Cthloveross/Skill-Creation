#!/usr/bin/env python3
"""Validate \left/\right delimiter structure for one formula JSON request."""
from __future__ import annotations

import json
import sys

from formula_tools import clean_formula, inspect_left_right


def main() -> None:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict) or "formula" not in request:
            raise ValueError("input must be an object with a formula field")
        formula, cleanup = clean_formula(request["formula"])
        result = {"formula": formula, "cleanup": cleanup, **inspect_left_right(formula)}
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}))
        sys.exit(2)


if __name__ == "__main__":
    main()
