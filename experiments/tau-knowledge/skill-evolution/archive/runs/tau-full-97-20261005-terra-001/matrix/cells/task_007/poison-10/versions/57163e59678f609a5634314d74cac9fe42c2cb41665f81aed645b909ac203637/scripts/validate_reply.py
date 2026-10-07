#!/usr/bin/env python3
"""Check a proposed comparison response against caller-supplied text requirements.

Input and output are JSON objects. This helper performs deterministic text checks only;
it does not decide factual support or customer eligibility.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict, List


def string_list(value: Any, field: str, errors: List[str]) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{field} must be an array of strings")
        return []
    return value


def matching_patterns(text: str, patterns: List[str], errors: List[str], field: str) -> List[str]:
    matches: List[str] = []
    for pattern in patterns:
        try:
            if re.search(pattern, text, flags=re.IGNORECASE):
                matches.append(pattern)
        except re.error as exc:
            errors.append(f"Invalid regex in {field}: {pattern!r}: {exc}")
    return matches


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    response = payload.get("response")
    if not isinstance(response, str):
        return {
            "valid": False,
            "missing_terms": [],
            "forbidden_matches": [],
            "warning_matches": [],
            "input_errors": ["response must be a string"],
        }

    required_terms = string_list(payload.get("required_terms"), "required_terms", errors)
    forbidden_patterns = string_list(payload.get("forbidden_patterns"), "forbidden_patterns", errors)
    warning_patterns = string_list(payload.get("warning_patterns"), "warning_patterns", errors)

    folded = response.casefold()
    missing = [term for term in required_terms if term.casefold() not in folded]
    forbidden = matching_patterns(response, forbidden_patterns, errors, "forbidden_patterns")
    warnings = matching_patterns(response, warning_patterns, errors, "warning_patterns")

    return {
        "valid": not errors and not missing and not forbidden,
        "missing_terms": missing,
        "forbidden_matches": forbidden,
        "warning_matches": warnings,
        "input_errors": errors,
    }


if __name__ == "__main__":
    try:
        value = json.load(sys.stdin)
        if not isinstance(value, dict):
            raise ValueError("Top-level JSON must be an object")
        print(json.dumps(main(value), indent=2, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "input_errors": [str(exc)]}))
        sys.exit(2)
