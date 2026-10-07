#!/usr/bin/env python3
"""Evaluate permitted identity claims and emit safe email-update tool actions.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
never calls banking tools; its action list is a recommendation for the executor.
"""

import datetime as dt
import json
import re
import sys
from typing import Any, Dict, List, Tuple

REQUIRED_RECORD_FIELDS = (
    "user_id",
    "name",
    "address",
    "email",
    "phone_number",
    "date_of_birth",
)
FACTOR_TO_CLAIM_KEY = {
    "date_of_birth": "date_of_birth",
    "email": "current_email",
    "phone_number": "phone_number",
    "address": "address",
}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def normalize_email(value: Any) -> str:
    return text(value).casefold()


def normalize_phone(value: Any) -> str:
    return "".join(ch for ch in text(value) if ch.isdigit())


def normalize_address(value: Any) -> str:
    return " ".join(text(value).casefold().split())


def normalize_dob(value: Any) -> str:
    value = text(value)
    try:
        return dt.datetime.strptime(value, "%m/%d/%Y").strftime("%m/%d/%Y")
    except ValueError:
        return ""


def normalized_factor(field: str, value: Any) -> str:
    if field == "email":
        return normalize_email(value)
    if field == "phone_number":
        return normalize_phone(value)
    if field == "address":
        return normalize_address(value)
    if field == "date_of_birth":
        return normalize_dob(value)
    return ""


def emit(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def main() -> None:
    try:
        raw = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        emit({"status": "invalid_input", "actions": [], "errors": [f"Invalid JSON: {exc}"]})
        return

    if not isinstance(raw, dict):
        emit({"status": "invalid_input", "actions": [], "errors": ["Top-level input must be an object."]})
        return

    record = raw.get("record")
    claims = raw.get("claims", {})
    new_email = text(raw.get("new_email"))
    time_verified = text(raw.get("time_verified"))
    errors: List[str] = []

    if not isinstance(record, dict):
        errors.append("record must be an object.")
        record = {}
    if not isinstance(claims, dict):
        errors.append("claims must be an object.")
        claims = {}

    for field in REQUIRED_RECORD_FIELDS:
        if not text(record.get(field)):
            errors.append(f"record.{field} is required.")
    if not EMAIL_RE.match(new_email):
        errors.append("new_email must be a plausibly formatted email address.")

    if errors:
        emit({"status": "invalid_input", "actions": [], "errors": errors})
        return

    matched: List[str] = []
    supplied: List[str] = []
    for factor, claim_key in FACTOR_TO_CLAIM_KEY.items():
        claim = claims.get(claim_key)
        normalized_claim = normalized_factor(factor, claim)
        if normalized_claim:
            supplied.append(factor)
            if normalized_claim == normalized_factor(factor, record.get(factor)):
                matched.append(factor)

    remaining = [factor for factor in FACTOR_TO_CLAIM_KEY if factor not in supplied]
    base: Dict[str, Any] = {
        "matched_fields": matched,
        "remaining_factor_options": remaining,
        "actions": [],
        "errors": [],
    }

    if len(matched) < 2:
        base["status"] = "need_more_verified_factors" if remaining else "identity_not_verified"
        emit(base)
        return

    if not time_verified:
        base["status"] = "invalid_input"
        base["errors"] = ["time_verified is required after calling get_current_time."]
        emit(base)
        return

    log_arguments = {
        "name": record["name"],
        "user_id": record["user_id"],
        "address": record["address"],
        "email": record["email"],
        "phone_number": record["phone_number"],
        "date_of_birth": record["date_of_birth"],
        "time_verified": time_verified,
    }

    if normalize_email(new_email) == normalize_email(record["email"]):
        base["status"] = "already_current"
        base["actions"] = [
            {
                "tool": "log_verification",
                "arguments": log_arguments,
                "purpose": "Create the required audit record for the successful verification.",
            }
        ]
        emit(base)
        return

    base["status"] = "verified"
    base["actions"] = [
        {
            "tool": "log_verification",
            "arguments": log_arguments,
            "purpose": "Create the required audit record for the successful verification.",
        },
        {
            "tool": "change_user_email",
            "arguments": {"user_id": record["user_id"], "new_email": new_email},
            "purpose": "Apply the requested email change only after verification logging succeeds.",
        },
    ]
    emit(base)


if __name__ == "__main__":
    main()
