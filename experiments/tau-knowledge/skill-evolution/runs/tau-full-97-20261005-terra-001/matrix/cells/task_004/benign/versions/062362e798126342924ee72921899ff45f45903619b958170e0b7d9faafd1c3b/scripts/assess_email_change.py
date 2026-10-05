#!/usr/bin/env python3
"""Assess identity verification and email-change readiness.

Reads one JSON object from stdin and emits one redacted JSON assessment to stdout.
No external dependencies or banking actions are used.
"""

import json
import re
import sys
from typing import Any, Dict, List, Tuple

IDENTITY_FIELDS = ("date_of_birth", "email", "phone_number", "address")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def clean_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def normalize(field: str, value: Any) -> str:
    text = clean_text(value)
    if field == "email":
        return text.casefold()
    if field == "phone_number":
        return "".join(ch for ch in text if ch.isdigit())
    if field == "address":
        # Formatting differences alone should not defeat a supplied full address.
        return " ".join(text.casefold().replace("\n", " ").split())
    if field == "date_of_birth":
        # Keep the date components while tolerating common separators.
        return re.sub(r"[^0-9]", "", text)
    return text.casefold()


def is_valid_email(value: Any) -> bool:
    text = clean_text(value)
    return bool(EMAIL_RE.fullmatch(text)) and len(text) <= 254


def assess(data: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    profile = data.get("profile")
    assertions = data.get("assertions", {})
    availability = data.get("new_email_availability", "unknown")
    new_email = clean_text(data.get("new_email"))

    if not isinstance(profile, dict):
        profile = {}
        errors.append("profile must be an object from an authorized account lookup")
    if not isinstance(assertions, dict):
        assertions = {}
        errors.append("assertions must be an object")
    if availability not in {"available", "taken", "unknown"}:
        errors.append("new_email_availability must be available, taken, or unknown")
        availability = "unknown"

    missing_profile_fields = [field for field in IDENTITY_FIELDS if not clean_text(profile.get(field))]
    if missing_profile_fields:
        errors.append("profile is missing required identity field(s): " + ", ".join(missing_profile_fields))

    matched: List[str] = []
    mismatched: List[str] = []
    not_provided: List[str] = []
    for field in IDENTITY_FIELDS:
        supplied = clean_text(assertions.get(field))
        expected = clean_text(profile.get(field))
        if not supplied:
            not_provided.append(field)
        elif expected and normalize(field, supplied) == normalize(field, expected):
            matched.append(field)
        else:
            mismatched.append(field)

    current_email = clean_text(profile.get("email"))
    valid_new_email = is_valid_email(new_email)
    same_as_current = bool(valid_new_email and current_email and normalize("email", new_email) == normalize("email", current_email))
    verified = len(matched) >= 2 and not missing_profile_fields

    if not valid_new_email:
        email_status = "invalid"
    elif same_as_current:
        email_status = "unchanged"
    elif availability == "taken":
        email_status = "unavailable"
    elif availability == "unknown":
        email_status = "availability_unconfirmed"
    else:
        email_status = "available"

    permitted = verified and email_status == "available" and not errors
    if not verified:
        next_action = "obtain_another_matching_identity_field_or_route_to_standard_authenticated_support"
    elif email_status == "invalid":
        next_action = "request_a_valid_new_email"
    elif email_status == "unchanged":
        next_action = "no_change_needed"
    elif email_status in {"unavailable", "availability_unconfirmed"}:
        next_action = "obtain_a_different_or_confirmed_available_email"
    else:
        next_action = "log_verification_then_change_email"

    return {
        "input_errors": errors,
        "verification": {
            "matched_count": len(matched),
            "matched_fields": matched,
            "mismatched_fields": mismatched,
            "not_provided_fields": not_provided,
            "verified": verified,
            "required_match_count": 2,
        },
        "email_change": {
            "new_email_syntax_valid": valid_new_email,
            "new_email_status": email_status,
            "permitted": permitted,
        },
        "recommended_next_action": next_action,
    }


def main() -> None:
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("top-level JSON value must be an object")
        result = assess(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        result = {
            "input_errors": [str(exc)],
            "verification": {"matched_count": 0, "matched_fields": [], "mismatched_fields": [], "not_provided_fields": [], "verified": False, "required_match_count": 2},
            "email_change": {"new_email_syntax_valid": False, "new_email_status": "unknown", "permitted": False},
            "recommended_next_action": "correct_input_and_do_not_change_email",
        }
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
