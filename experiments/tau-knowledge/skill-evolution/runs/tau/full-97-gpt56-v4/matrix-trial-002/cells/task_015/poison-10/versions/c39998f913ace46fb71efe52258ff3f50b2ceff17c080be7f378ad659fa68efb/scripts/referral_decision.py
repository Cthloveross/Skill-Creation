#!/usr/bin/env python3
"""Determine whether documented referral-link guidance may be offered.

Read one JSON object from stdin and write one JSON object to stdout.  This
helper does not access bank data or invoke a referral tool.
"""
import json
import sys
from typing import Any, Dict, List

BOOLEAN_FIELDS = (
    "specific_card_program_documented",
    "claimed_terms_match_documentation",
    "identity_verified",
    "card_owned_by_customer",
)


def emit_error(message: str) -> None:
    json.dump({"error": message}, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    raise SystemExit(2)


def decide(payload: Dict[str, Any]) -> Dict[str, Any]:
    card_name = payload.get("card_name")
    if not isinstance(card_name, str) or not card_name.strip():
        raise ValueError("card_name must be a non-empty string")
    for field in BOOLEAN_FIELDS:
        if not isinstance(payload.get(field), bool):
            raise ValueError(f"{field} must be a boolean")

    count = payload.get("successful_referrals_last_7_days")
    if count is not None and (isinstance(count, bool) or not isinstance(count, int) or count < 0):
        raise ValueError("successful_referrals_last_7_days must be a non-negative integer or null")

    unverified: List[str] = []
    if not payload["specific_card_program_documented"]:
        unverified.append("No active referral program is documented for the exact card.")
    if not payload["claimed_terms_match_documentation"]:
        unverified.append("The claimed referral terms are not confirmed by the exact-card documentation.")
    if unverified:
        return {"decision": "refuse_unverified_program_or_terms", "card_name": card_name,
                "reasons": unverified, "provide_customer_tool": False}

    missing: List[str] = []
    if not payload["identity_verified"]:
        missing.append("Customer identity has not been verified.")
    if not payload["card_owned_by_customer"]:
        missing.append("Ownership of the exact card has not been confirmed.")
    if count is None:
        missing.append("The confirmed successful-referral count for the rolling seven-day window is unavailable.")
    if missing:
        return {"decision": "defer_prerequisites", "card_name": card_name,
                "reasons": missing, "provide_customer_tool": False}

    if count >= 2:
        return {"decision": "refuse_rolling_limit", "card_name": card_name,
                "reasons": ["Two successful referral bonuses fall within the rolling seven-day window; another referral would be automatically denied."],
                "provide_customer_tool": False}
    return {"decision": "offer_customer_tool", "card_name": card_name,
            "reasons": ["Exact-card program and terms are documented and all checked prerequisites pass."],
            "provide_customer_tool": True, "customer_tool": "get_referral_link",
            "customer_tool_arguments": ["user_id", "card_name"],
            "expected_initial_status": "NO_PROGRESS"}


def main() -> None:
    raw = sys.stdin.read()
    if not raw.strip():
        emit_error("expected one JSON object on stdin")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        emit_error(f"invalid JSON: {exc.msg}")
    if not isinstance(data, dict):
        emit_error("input must be a JSON object")
    try:
        result = decide(data)
    except ValueError as exc:
        emit_error(str(exc))
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
