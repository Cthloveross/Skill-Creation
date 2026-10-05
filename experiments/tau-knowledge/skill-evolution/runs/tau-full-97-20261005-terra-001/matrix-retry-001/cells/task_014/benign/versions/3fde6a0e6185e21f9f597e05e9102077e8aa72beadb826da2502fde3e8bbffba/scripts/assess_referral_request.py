#!/usr/bin/env python3
"""Deterministically gate a customer-operated credit-card referral-link offer.

Reads one JSON object from stdin and emits one JSON object to stdout. This helper
never searches for programs, retrieves customer data, or calls a banking tool.
"""

import json
import sys
from typing import Any, Dict, List, Tuple


def emit(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def invalid(message: str) -> None:
    emit({
        "decision": "INVALID_INPUT",
        "may_offer_user_tool": False,
        "message": message,
    })


def is_plain_object(value: Any) -> bool:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def canonical(value: Any) -> Any:
    """Compare supplied JSON terms without semantic or unit inference."""
    if isinstance(value, str):
        return " ".join(value.split()).casefold()
    if isinstance(value, list):
        return [canonical(item) for item in value]
    if isinstance(value, dict):
        return {key: canonical(value[key]) for key in sorted(value)}
    return value


def validate_input(data: Any) -> Tuple[bool, str]:
    if not is_plain_object(data):
        return False, "Input must be a JSON object."

    required = {
        "requested_card_name",
        "card_identity_confirmed",
        "documented_program",
        "claimed_terms",
        "customer_confirmed_documented_terms",
        "automatic_rejection_expected",
    }
    missing = sorted(required - set(data))
    if missing:
        return False, "Missing required field(s): " + ", ".join(missing)

    if not isinstance(data["requested_card_name"], str):
        return False, "requested_card_name must be a string."
    for key in (
        "card_identity_confirmed",
        "customer_confirmed_documented_terms",
        "automatic_rejection_expected",
    ):
        if not isinstance(data[key], bool):
            return False, key + " must be a boolean."
    if not is_plain_object(data["claimed_terms"]):
        return False, "claimed_terms must be an object."

    program = data["documented_program"]
    if program is not None:
        if not is_plain_object(program):
            return False, "documented_program must be an object or null."
        for key in ("card_name", "active", "terms"):
            if key not in program:
                return False, "documented_program is missing " + key + "."
        if not isinstance(program["card_name"], str):
            return False, "documented_program.card_name must be a string."
        if not isinstance(program["active"], bool):
            return False, "documented_program.active must be a boolean."
        if not is_plain_object(program["terms"]):
            return False, "documented_program.terms must be an object."

    if data["automatic_rejection_expected"]:
        reason = data.get("automatic_rejection_reason")
        if not isinstance(reason, str) or not reason.strip():
            return False, (
                "automatic_rejection_reason is required when automatic rejection "
                "is expected."
            )
    return True, ""


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        invalid("Could not read input JSON: " + str(exc))
        return

    valid, error = validate_input(data)
    if not valid:
        invalid(error)
        return

    program = data["documented_program"]
    if program is None or not data["card_identity_confirmed"] or not program["active"]:
        emit({
            "decision": "REFUSE_NO_ACTIVE_DOCUMENTED_PROGRAM",
            "may_offer_user_tool": False,
            "message": (
                "No active, card-specific documented referral program has been "
                "confirmed for the requested card."
            ),
        })
        return

    documented_terms = program["terms"]
    mismatched: List[str] = []
    for key, claimed_value in data["claimed_terms"].items():
        if key not in documented_terms or canonical(claimed_value) != canonical(documented_terms[key]):
            mismatched.append(key)

    common = {
        "documented_card_name": program["card_name"],
        "documented_terms": documented_terms,
    }
    if mismatched:
        emit({
            "decision": "REFUSE_TERMS_MISMATCH",
            "may_offer_user_tool": False,
            "mismatched_term_keys": sorted(mismatched),
            "message": "One or more customer-stated terms do not match the active documented program.",
            **common,
        })
        return

    if data["automatic_rejection_expected"]:
        emit({
            "decision": "REFUSE_AUTOMATIC_DENIAL",
            "may_offer_user_tool": False,
            "automatic_rejection_reason": data["automatic_rejection_reason"].strip(),
            "message": "The available information indicates the referral would be automatically denied.",
            **common,
        })
        return

    if not data["customer_confirmed_documented_terms"]:
        emit({
            "decision": "NEEDS_CUSTOMER_TERM_CONFIRMATION",
            "may_offer_user_tool": False,
            "message": "The documented terms must be restated and confirmed before a referral link is offered.",
            **common,
        })
        return

    emit({
        "decision": "OFFER_CUSTOMER_OPERATED_TOOL",
        "may_offer_user_tool": True,
        "discoverable_tool_name": "get_referral_link",
        "message": (
            "The customer may be offered the user-operated referral-link tool after "
            "being reminded of the rolling seven-day two-bonus limit."
        ),
        **common,
    })


if __name__ == "__main__":
    main()
