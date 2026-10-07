#!/usr/bin/env python3
"""Conservatively assess whether a referral-link tool may be offered.

Reads a JSON object from stdin and writes a JSON object to stdout. This helper
makes no external calls and does not generate a referral link.
"""

import json
import sys
from datetime import date, datetime
from typing import Any, Optional


def parse_date(value: Any) -> Optional[date]:
    """Parse an ISO date or a timestamp whose first 10 characters are a date."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("date must be a string or null")
    candidate = value.strip()[:10]
    if not candidate:
        return None
    try:
        return date.fromisoformat(candidate)
    except ValueError:
        # Support a full ISO datetime if a caller supplies one.
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).date()
        except ValueError as exc:
            raise ValueError("date must begin with YYYY-MM-DD or be ISO-8601") from exc


def assess(payload: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    documented = payload.get("documented") is True
    terms_match = payload.get("terms_match") is True
    rejection_reason = payload.get("automatic_rejection_reason")

    if not documented:
        reasons.append("No documented referral program is available for the requested offer.")
    if not terms_match:
        reasons.append("The stated terms do not match the documented referral offer.")
    if rejection_reason not in (None, ""):
        reasons.append("A documented rejection condition applies: " + str(rejection_reason))

    try:
        current = parse_date(payload.get("current_date"))
    except ValueError as exc:
        current = None
        reasons.append("Current date is invalid: " + str(exc))
    if current is None:
        reasons.append("A current date is required to assess offer availability.")

    try:
        deadline = parse_date(payload.get("submission_deadline"))
    except ValueError as exc:
        deadline = None
        reasons.append("Submission deadline is invalid: " + str(exc))

    if current is not None and deadline is not None and current > deadline:
        reasons.append("The documented referral-submission deadline has passed.")

    allowed = (
        documented
        and terms_match
        and not rejection_reason
        and current is not None
        and (deadline is None or current <= deadline)
    )
    return {
        "decision": "offer_link_tool" if allowed else "do_not_offer_link_tool",
        "reasons": reasons,
        "current_date": current.isoformat() if current else None,
        "submission_deadline": deadline.isoformat() if deadline else None,
    }


def main() -> None:
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(assess(raw), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({
            "decision": "do_not_offer_link_tool",
            "reasons": ["Unable to assess referral offer: " + str(exc)],
            "current_date": None,
            "submission_deadline": None,
        }, sort_keys=True))


if __name__ == "__main__":
    main()
