#!/usr/bin/env python3
"""Deterministically decide whether referral-link guidance may be offered.

Reads one JSON object from stdin and writes one JSON object to stdout.
This script neither accesses bank data nor calls referral tools.
"""

import json
import sys
from typing import Any, Dict, List

REQUIRED_BOOLEAN_FIELDS = (
    "specific_card_program_documented",
    "claimed_terms_match_documentation",
    "identity_verified",
    "card_owned_by_customer",
)


def fail(message: str) -> None:
    json.dump({"error": message}, sys.stdout)
    sys.stdout.write("\n")
    raise SystemExit(2)


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    card_name = payload.get("card_name")
    if not isinstance(card_name, str) or not card_name.strip():
        raise ValueError("card_name must be a non-empty string")

    for field in REQUIRED_BOOLEAN_FIELDS:
        if not isinstance(payload.get(field), bool):
            raise ValueError(f"{field} must be a boolean")

    count = payload.get("successful_referrals_last_7_days")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("successful_referrals_last_7_days must be a non-negative integer")

    reasons: List[str] = []
    if not payload["specific_card_program_documented"]:
        reasons.append("No active referral program is documented for the exact card.")
    if not payload["claimed_terms_match_documentation"]:
        reasons.append("The claimed referral terms are not confirmed by documented terms.")
    if reasons:
        return {
            "decision": "refuse_unverified_program_or_terms",
            "card_name": card_name,
            "reasons": reasons,
            "provide_customer_tool": False,
        }

    prerequisites: List[str] = []
    if not payload["identity_verified"]:
        prerequisites.append("Customer identity has not been verified.")
    if not payload["card_owned_by_customer"]:
        prerequisites.append("Ownership of the stated card has not been confirmed.")
    if prerequisites:
        return {
            "decision": "defer_identity_or_ownership",
            "card_name": card_name,
            "reasons": prerequisites,
            "provide_customer_tool": False,
        }

    if count >= 2:
        return {
            "decision": "refuse_rolling_limit",
            "card_name": card_name,
            "reasons": [
                "Two successful referral bonuses already fall within the rolling seven-day window; an additional referral would be automatically denied."
            ],
            "provide_customer_tool": False,
        }

    return {
        "decision": "offer_customer_tool",
        "card_name": card_name,
        "reasons": [
            "The exact card program and terms are documented, identity and ownership are confirmed, and the known rolling-seven-day count is below two."
        ],
        "provide_customer_tool": True,
        "customer_tool": "get_referral_link",
        "customer_tool_arguments": ["user_id", "card_name"],
        "expected_initial_status": "NO_PROGRESS",
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            fail("expected one JSON object on stdin")
        data = json.loads(raw)
        if not isinstance(data, dict):
            fail("input must be a JSON object")
        result = main(data)
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON: {exc.msg}")
    except ValueError as exc:
        fail(str(exc))
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
