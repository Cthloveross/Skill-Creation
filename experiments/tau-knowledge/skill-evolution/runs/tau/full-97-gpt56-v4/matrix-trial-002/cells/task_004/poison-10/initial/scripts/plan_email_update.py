#!/usr/bin/env python3
"""Select a safe next step for an authenticated profile-email-update workflow.

Reads one JSON object from stdin and emits one JSON object to stdout. This helper
never accesses bank data and never performs banking actions.
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def emit(action: str, reason: str, message: str) -> None:
    print(json.dumps({"action": action, "reason": reason, "message": message}, sort_keys=True))


def main(payload: dict[str, Any]) -> None:
    if payload.get("request_type") != "email_update":
        emit("reject_invalid_input", "unsupported_request_type",
             "This helper is limited to profile email-update requests.")
        return

    requested_human = payload.get("requested_human", False)
    unresolved = payload.get("unresolved", False)
    if not isinstance(requested_human, bool) or not isinstance(unresolved, bool):
        emit("reject_invalid_input", "invalid_boolean", "requested_human and unresolved must be booleans.")
        return
    if requested_human:
        reason = ("customer_frustrated_demands_human" if unresolved
                  else "customer_requests_human_no_specific_reason")
        emit("transfer_to_human", reason,
             "Transfer now; summarize the request and completed steps without further troubleshooting.")
        return

    email = payload.get("new_email")
    if not isinstance(email, str) or not EMAIL_PATTERN.fullmatch(email.strip()):
        emit("reject_invalid_input", "missing_or_invalid_email",
             "Obtain and confirm a valid new email address before proceeding.")
        return

    fields = payload.get("authenticated_fields", 0)
    if isinstance(fields, bool) or not isinstance(fields, int) or not 0 <= fields <= 4:
        emit("reject_invalid_input", "invalid_authenticated_fields",
             "authenticated_fields must be an integer from 0 through 4.")
        return
    if fields < 2:
        emit("collect_identity", "two_matching_fields_required",
             "Obtain independent confirmation of enough identity fields to reach two matches before discussing details or updating email.")
        return

    logged = payload.get("verification_logged", False)
    if not isinstance(logged, bool):
        emit("reject_invalid_input", "invalid_verification_logged", "verification_logged must be a boolean.")
        return
    if not logged:
        emit("log_verification", "audit_record_required",
             "Retrieve the current timestamp and create the verification audit record before changing the email.")
        return

    available = payload.get("email_is_available")
    if available is None:
        emit("check_email_availability", "availability_not_checked",
             "Check whether the requested email is already associated with another user.")
    elif available is False:
        emit("request_different_email", "email_already_in_use",
             "Do not overwrite another user's email; request a different address or transfer if requested.")
    elif available is True:
        emit("change_email", "requirements_satisfied",
             "Call the normal email-change tool for the verified user and confirm a successful result.")
    else:
        emit("reject_invalid_input", "invalid_email_is_available", "email_is_available must be true, false, or null.")


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("top-level JSON must be an object")
        main(data)
    except (json.JSONDecodeError, ValueError) as exc:
        emit("reject_invalid_input", "invalid_json", str(exc))
