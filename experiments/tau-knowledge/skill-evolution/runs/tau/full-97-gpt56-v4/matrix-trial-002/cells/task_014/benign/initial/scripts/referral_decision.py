#!/usr/bin/env python3
"""Conservatively decide whether a referral-link tool may be offered.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
makes no banking calls and never generates a referral link.
"""

import json
import sys
from typing import Any, Dict, List


def as_confirmed_bool(value: Any) -> bool:
    """Only the JSON boolean true is a confirmed affirmative."""
    return value is True


def decide(payload: Dict[str, Any]) -> Dict[str, Any]:
    documented = as_confirmed_bool(payload.get("card_program_documented"))
    terms_match = as_confirmed_bool(payload.get("terms_match"))
    auto_reject = as_confirmed_bool(payload.get("automatic_rejection_expected"))

    reasons: List[str] = []
    if not documented:
        reasons.append("No referral program is confirmed for the exact requested card.")
    if not terms_match:
        reasons.append("The customer's claimed referral terms are not confirmed to match documented terms.")
    if auto_reject:
        reasons.append("The referral is expected to be automatically rejected.")

    card_name = payload.get("card_name")
    context: Dict[str, Any] = {}
    if isinstance(card_name, str) and card_name.strip():
        context["card_name"] = card_name.strip()
    notes = payload.get("notes")
    if isinstance(notes, list):
        context["notes"] = [item for item in notes if isinstance(item, str)]

    if reasons:
        return {
            "decision": "refuse_link",
            "reasons": reasons,
            "next_step": (
                "Explain the applicable unconfirmed, mismatched, or automatic-rejection "
                "reason. Do not expose or generate a referral link and do not transfer "
                "solely for this unavailable offer."
            ),
            "context": context,
        }

    return {
        "decision": "offer_user_tool",
        "reasons": [],
        "next_step": (
            "Restate the documented terms and rolling seven-day limit, then expose "
            "get_referral_link for the customer to run themselves with their own user_id "
            "and the exact card name. Do not call it for them."
        ),
        "context": context,
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid_json", "message": str(exc)}))
        raise SystemExit(2)
    if not isinstance(payload, dict):
        print(json.dumps({"error": "invalid_input", "message": "Expected a JSON object."}))
        raise SystemExit(2)
    print(json.dumps(decide(payload), sort_keys=True))


if __name__ == "__main__":
    main()
