#!/usr/bin/env python3
"""Validate an email-change request without contacting banking systems.

Input JSON object:
  new_email: string
  confirmations: object with any of date_of_birth, email, phone_number, address
  record: optional object with the same four stored fields

Output JSON object:
  valid_new_email: bool
  matched_fields: list[str]
  verification_sufficient: bool
  errors: list[str]

Only two matching fields among date_of_birth, email, phone_number, and address
constitute sufficient verification. Callers must still create the required audit log
and use banking tools to make any change.
"""
import json
import re
import sys
from typing import Any, Dict, List

FIELDS = ("date_of_birth", "email", "phone_number", "address")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def normalize(field: str, value: Any) -> str:
    value = text(value)
    if field == "email":
        return value.casefold()
    if field == "phone_number":
        return "".join(ch for ch in value if ch.isdigit())
    if field == "address":
        return " ".join(value.casefold().split())
    return value


def validate(payload: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    new_email = text(payload.get("new_email"))
    valid_new_email = bool(EMAIL_RE.fullmatch(new_email)) and len(new_email) <= 254
    if not valid_new_email:
        errors.append("new_email must be a syntactically valid email address")

    confirmations = payload.get("confirmations", {})
    record = payload.get("record", {})
    if not isinstance(confirmations, dict):
        confirmations = {}
        errors.append("confirmations must be an object")
    if record is not None and not isinstance(record, dict):
        record = {}
        errors.append("record must be an object when provided")

    matched: List[str] = []
    if not record:
        errors.append("stored record values are required to evaluate verification")
    else:
        for field in FIELDS:
            supplied = normalize(field, confirmations.get(field))
            stored = normalize(field, record.get(field))
            if supplied and stored and supplied == stored:
                matched.append(field)

    return {
        "valid_new_email": valid_new_email,
        "matched_fields": matched,
        "verification_sufficient": len(matched) >= 2,
        "errors": errors,
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        result = validate(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        result = {
            "valid_new_email": False,
            "matched_fields": [],
            "verification_sufficient": False,
            "errors": [str(exc)],
        }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
