#!/usr/bin/env python3
"""Classify two-of-four banking identity-verification evidence.

Reads a JSON object from stdin and emits a JSON object on stdout. This helper
never accesses profile data and never performs a banking action.
"""

import json
import sys

QUALIFYING_FIELDS = ("date_of_birth", "email", "phone_number", "address")
VALID_STATES = {"match", "mismatch", "unknown"}


def emit(value: dict) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        emit({"error": "invalid_json", "message": str(exc)})
        return

    if not isinstance(payload, dict):
        emit({"error": "invalid_input", "message": "input must be a JSON object"})
        return

    responses = payload.get("responses", {})
    if not isinstance(responses, dict):
        emit({"error": "invalid_input", "message": "responses must be an object"})
        return

    unknown_fields = sorted(set(responses) - set(QUALIFYING_FIELDS))
    if unknown_fields:
        emit({
            "error": "invalid_field",
            "message": "responses contains unsupported qualifying field names",
            "fields": unknown_fields,
        })
        return

    normalized = {}
    for field in QUALIFYING_FIELDS:
        state = responses.get(field, "unknown")
        if state not in VALID_STATES:
            emit({
                "error": "invalid_state",
                "message": "each response state must be match, mismatch, or unknown",
                "field": field,
            })
            return
        normalized[field] = state

    confirmed = [field for field in QUALIFYING_FIELDS if normalized[field] == "match"]
    mismatched = [field for field in QUALIFYING_FIELDS if normalized[field] == "mismatch"]

    if mismatched:
        result = {
            "confirmed_fields": confirmed,
            "mismatched_fields": mismatched,
            "verification_status": "failed",
            "should_log_verification": False,
            "recommended_next_step": "transfer_to_specialist_account_ownership_dispute",
        }
    elif len(confirmed) >= 2:
        result = {
            "confirmed_fields": confirmed,
            "mismatched_fields": [],
            "verification_status": "verified",
            "should_log_verification": True,
            "recommended_next_step": "log_verification_then_begin_pin_lock_investigation",
        }
    else:
        result = {
            "confirmed_fields": confirmed,
            "mismatched_fields": [],
            "verification_status": "incomplete",
            "should_log_verification": False,
            "recommended_next_step": "request_one_additional_qualifying_field",
        }

    emit(result)


if __name__ == "__main__":
    main()
