#!/usr/bin/env python3
"""Evaluate prerequisites for a verified account-email update.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
is intentionally read-only: the calling agent must invoke banking tools for lookup,
audit logging, and the actual email change.
"""

import datetime as _datetime
import json
import re
import sys
from typing import Any, Dict, Optional

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_REQUIRED_ACCOUNT_FIELDS = (
    "user_id",
    "name",
    "address",
    "email",
    "phone_number",
    "date_of_birth",
)
_IDENTITY_FIELDS = ("date_of_birth", "email", "phone_number", "address")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _normal_email(value: Any) -> Optional[str]:
    value = _text(value)
    if not value or len(value) > 254 or not _EMAIL_RE.fullmatch(value):
        return None
    return value.casefold()


def _normal_phone(value: Any) -> Optional[str]:
    digits = "".join(ch for ch in _text(value) if ch.isdigit())
    # North-American tool data normally contains ten digits. Retain a leading 1
    # only as a presentation prefix, so both common customer formats compare.
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def _normal_date(value: Any) -> Optional[str]:
    value = _text(value)
    try:
        return _datetime.datetime.strptime(value, "%m/%d/%Y").strftime("%m/%d/%Y")
    except ValueError:
        return None


def _normal_address(value: Any) -> Optional[str]:
    value = _text(value).casefold()
    if not value:
        return None
    # Ignore case, punctuation, and spacing only; do not invent street aliases.
    normalized = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    normalized = " ".join(normalized.split())
    return normalized or None


def _identity_matches(account: Dict[str, Any], claims: Dict[str, Any]) -> int:
    comparisons = (
        (_normal_date(account.get("date_of_birth")), _normal_date(claims.get("date_of_birth"))),
        (_normal_email(account.get("email")), _normal_email(claims.get("email"))),
        (_normal_phone(account.get("phone_number")), _normal_phone(claims.get("phone_number"))),
        (_normal_address(account.get("address")), _normal_address(claims.get("address"))),
    )
    return sum(1 for stored, claimed in comparisons if stored is not None and claimed is not None and stored == claimed)


def _result(status: str, **extra: Any) -> Dict[str, Any]:
    output: Dict[str, Any] = {"status": status}
    output.update(extra)
    return output


def evaluate(payload: Dict[str, Any]) -> Dict[str, Any]:
    account = payload.get("account")
    claims = payload.get("claims", {})
    if not isinstance(account, dict) or not isinstance(claims, dict):
        return _result("invalid_input", message="account and claims must be JSON objects")

    missing = [field for field in _REQUIRED_ACCOUNT_FIELDS if not _text(account.get(field))]
    if missing:
        return _result(
            "unsupported_incomplete_account_record",
            message="The selected account record lacks fields required for verification logging.",
            missing_account_fields=missing,
        )

    requested_email = _normal_email(payload.get("new_email"))
    if requested_email is None:
        return _result(
            "need_valid_new_email",
            message="Obtain a complete, syntactically valid replacement email address before continuing.",
        )

    matches = _identity_matches(account, claims)
    verification = {
        "matches_required": 2,
        "matches_found": matches,
        "verified": matches >= 2,
    }
    if matches < 2:
        return _result(
            "need_additional_identity_field",
            message="Obtain another customer-stated current identity field without revealing stored values.",
            verification=verification,
            accepted_claim_fields=list(_IDENTITY_FIELDS),
        )

    timestamp = _text(payload.get("time_verified"))
    if not timestamp:
        return _result(
            "need_verification_timestamp",
            message="Call get_current_time and provide its returned timestamp before logging verification.",
            verification=verification,
        )

    # Compare normalized forms so email-capitalization differences do not create
    # a needless mutation. Authentication was still required above.
    if requested_email == _normal_email(account.get("email")):
        return _result(
            "no_change_needed",
            message="The requested email is already the current account email after verification.",
            verification=verification,
        )

    log_arguments = {
        "name": _text(account["name"]),
        "user_id": _text(account["user_id"]),
        "address": _text(account["address"]),
        "email": _text(account["email"]),
        "phone_number": _text(account["phone_number"]),
        "date_of_birth": _text(account["date_of_birth"]),
        "time_verified": timestamp,
    }
    return _result(
        "ready_to_log_and_change",
        message="Verification prerequisites are satisfied; log verification before changing the email.",
        verification=verification,
        log_verification_arguments=log_arguments,
        change_user_email_arguments={
            "user_id": _text(account["user_id"]),
            "new_email": _text(payload.get("new_email")),
        },
    )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON value must be an object")
        output = evaluate(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        output = _result("invalid_input", message=str(exc))
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
