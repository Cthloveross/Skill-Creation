#!/usr/bin/env python3
"""Evaluate a two-of-four identity-verification gate without echoing PII."""

import datetime as _dt
import json
import re
import sys

FIELDS = ("date_of_birth", "email", "phone_number", "address")


def _text(value):
    return value.strip() if isinstance(value, str) else None


def _normalise(field, value):
    value = _text(value)
    if not value:
        return None
    if field == "date_of_birth":
        try:
            return _dt.datetime.strptime(value, "%m/%d/%Y").strftime("%m/%d/%Y")
        except ValueError:
            return "!invalid-date:" + value
    if field == "email":
        return value.casefold()
    if field == "phone_number":
        digits = re.sub(r"\D", "", value)
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        return digits or None
    # Ignore only presentation differences, not address content.
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _fail(message):
    print(json.dumps({"error": message}, sort_keys=True))
    return 2


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        return _fail("input must be one JSON object")
    if not isinstance(data, dict):
        return _fail("input must be one JSON object")

    profile = data.get("profile")
    claims = data.get("claims")
    exhausted = data.get("attempts_exhausted")
    if not isinstance(profile, dict) or not isinstance(claims, dict):
        return _fail("profile and claims must be JSON objects")
    if not isinstance(exhausted, bool):
        return _fail("attempts_exhausted must be boolean")

    supplied = []
    matched = []
    mismatched = []
    for field in FIELDS:
        raw_claim = claims.get(field)
        claim = _normalise(field, raw_claim)
        record = _normalise(field, profile.get(field))
        if claim is None:
            continue
        supplied.append(field)
        if record is not None and claim == record and not claim.startswith("!invalid-date:"):
            matched.append(field)
        else:
            mismatched.append(field)

    if len(matched) >= 2:
        result = {
            "verification_status": "verified",
            "matched_field_names": matched,
            "failed_field_names": mismatched,
            "next_step": "Log successful verification, then continue the authorized PIN-lock workflow.",
            "do_not_disclose_profile_values": True,
        }
    elif exhausted or (len(supplied) == len(FIELDS) and len(matched) < 2):
        result = {
            "verification_status": "identity_verification_failed",
            "matched_field_names": matched,
            "failed_field_names": mismatched,
            "transfer_reason": "account_ownership_dispute",
            "transfer_summary": "Caller requested assistance with PIN-locked debit card(s), but identity verification could not be completed. No card action was taken; specialist verification is required.",
            "next_step": "Do not perform card lookup or card action; transfer to a human specialist.",
            "do_not_disclose_profile_values": True,
        }
    else:
        remaining = [field for field in FIELDS if field not in supplied]
        result = {
            "verification_status": "additional_identity_field_required",
            "matched_field_names": matched,
            "failed_field_names": mismatched,
            "remaining_permitted_field_names": remaining,
            "next_step": "Request another permitted identity field without revealing any profile value.",
            "do_not_disclose_profile_values": True,
        }

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
