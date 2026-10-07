#!/usr/bin/env python3
"""Assess supplied identity claims against a resolved user record.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
is deliberately read-only: it does not call banking tools or persist personal data.
"""

import json
import re
import sys
from typing import Any, Dict

SUPPORTED = ("date_of_birth", "email", "phone_number", "address")


def text_normalize(value: Any) -> str:
    """Normalize ordinary textual identity fields without guessing missing data."""
    return " ".join(str(value).strip().split()).casefold()


def normalize(field: str, value: Any) -> str:
    if value is None:
        return ""
    if field == "phone_number":
        return "".join(re.findall(r"\d", str(value)))
    return text_normalize(value)


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    record = payload.get("record")
    claims = payload.get("claims")
    if not isinstance(record, dict) or not isinstance(claims, dict):
        raise ValueError("'record' and 'claims' must both be JSON objects")

    matched = []
    mismatched = []
    not_provided = []
    unavailable_in_record = []

    for field in SUPPORTED:
        if field not in claims or claims[field] is None or not str(claims[field]).strip():
            not_provided.append(field)
            continue
        stored = normalize(field, record.get(field))
        supplied = normalize(field, claims[field])
        if not stored:
            unavailable_in_record.append(field)
        elif supplied == stored:
            matched.append(field)
        else:
            mismatched.append(field)

    return {
        "matched_fields": matched,
        "mismatched_fields": mismatched,
        "not_provided_fields": not_provided,
        "unavailable_in_record_fields": unavailable_in_record,
        "matched_count": len(matched),
        "verified": len(matched) >= 2,
    }


if __name__ == "__main__":
    try:
        parsed = json.load(sys.stdin)
        if not isinstance(parsed, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(parsed), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
