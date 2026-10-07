#!/usr/bin/env python3
"""Check supplied identity claims against one already-resolved customer record.

Reads JSON from stdin and writes JSON to stdout. It never looks up accounts or
writes verification logs; the banking executor must perform those steps.
"""
import json
import re
import sys

FIELDS = ("date_of_birth", "email", "phone_number", "address")


def normalize(field, value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    if field == "email":
        return value.casefold()
    if field == "phone_number":
        digits = re.sub(r"\D", "", value)
        return digits or None
    if field == "address":
        return " ".join(value.split()).casefold()
    if field == "date_of_birth":
        # The banking record format is MM/DD/YYYY. Do not guess ambiguous dates.
        return value if re.fullmatch(r"\d{2}/\d{2}/\d{4}", value) else None
    return value


def main(payload):
    record = payload.get("record")
    claims = payload.get("claims")
    if not isinstance(record, dict) or not isinstance(claims, dict):
        raise ValueError("record and claims must be JSON objects")

    matched = []
    supplied = []
    for field in FIELDS:
        if field not in claims:
            continue
        supplied.append(field)
        claim = normalize(field, claims.get(field))
        stored = normalize(field, record.get(field))
        if claim is not None and stored is not None and claim == stored:
            matched.append(field)
    return {
        "verified": len(matched) >= 2,
        "matched_count": len(matched),
        "matched_fields": matched,
        "supplied_fields": supplied,
    }


if __name__ == "__main__":
    try:
        body = json.load(sys.stdin)
        if not isinstance(body, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(body), ensure_ascii=False))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
