#!/usr/bin/env python3
"""Produce a conservative workflow plan for a verified bank email update.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
performs no banking operations and does not retain input data.
"""
import json
import re
import sys

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ALLOWED_OWNER_STATUSES = {"unknown", "none", "same_user", "different_user"}


def emit(status, next_step, may_change_email=False, errors=None):
    result = {
        "status": status,
        "next_step": next_step,
        "may_change_email": may_change_email,
    }
    if errors:
        result["errors"] = errors
    print(json.dumps(result, separators=(",", ":")))


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        emit("invalid_input", "Provide one valid JSON object.", errors=["invalid JSON"])
        return
    if not isinstance(payload, dict):
        emit("invalid_input", "Provide a JSON object.", errors=["input must be an object"])
        return

    identifier = payload.get("user_id") or payload.get("account_name")
    requested = payload.get("requested_email")
    owner_status = payload.get("email_owner_status", "unknown")
    matched_count = payload.get("matched_identity_field_count", 0)
    logged = payload.get("verification_logged", False)

    if not isinstance(identifier, str) or not identifier.strip():
        emit("need_identification", "Obtain a name or user ID and retrieve one unique user record.")
        return
    if not isinstance(requested, str) or not EMAIL_RE.fullmatch(requested.strip()):
        emit("invalid_requested_email", "Ask for a valid replacement email address.")
        return
    if owner_status not in ALLOWED_OWNER_STATUSES:
        emit("invalid_input", "Use an email_owner_status returned by the email lookup workflow.", errors=["unrecognized email_owner_status"])
        return
    if owner_status == "unknown":
        emit("need_email_lookup", "Look up the requested email to determine whether it is available.")
        return
    if owner_status == "different_user":
        emit("email_unavailable", "Do not change the profile; request another email or use support.")
        return
    if owner_status == "same_user":
        emit("no_change_needed", "Tell the customer that this is already the profile email.")
        return
    if not isinstance(matched_count, int) or isinstance(matched_count, bool) or matched_count < 0:
        emit("invalid_input", "Provide a nonnegative integer count of matched, distinct identity fields.", errors=["invalid matched_identity_field_count"])
        return
    if matched_count < 2:
        emit("need_identity_verification", "Obtain and match two distinct customer-provided identity fields.")
        return
    if logged is not True:
        emit("need_verification_log", "Get the current time and successfully log verification using the retrieved record.")
        return
    emit("ready_for_change", "Call change_user_email once with the identified user ID and requested email.", may_change_email=True)


if __name__ == "__main__":
    main()
