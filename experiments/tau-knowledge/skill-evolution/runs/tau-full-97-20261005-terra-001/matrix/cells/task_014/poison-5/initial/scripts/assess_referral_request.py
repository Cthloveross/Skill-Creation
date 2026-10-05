#!/usr/bin/env python3
"""Deterministically assess whether a referral-link tool may be offered.

Reads one JSON object from stdin and writes one JSON object to stdout. This script
has no network or banking-tool access and does not create a referral link.

Input schema:
{
  "card_name": str,
  "claimed_terms": object|null,
  "documented_program": bool,
  "documented_terms": object|null,
  "automatic_rejection": bool,
  "rejection_reason": str (optional)
}

Term objects contain normalized field names chosen by the caller, such as reward,
qualification, spend_requirement, and timeframe. Values are compared after case,
whitespace, and punctuation normalization. Every customer-claimed term must occur
with an equal documented value; extra documented fields are allowed.
"""
import json
import re
import sys
from typing import Any, Dict


def normalize(value: Any) -> str:
    """Normalize a scalar term value for a conservative textual comparison."""
    text = str(value).casefold().strip()
    return re.sub(r"[^\w]+", "", text)


def terms_match(claimed: Any, documented: Any) -> bool:
    """Require each claimed structured term to be documented identically."""
    if not isinstance(claimed, dict) or not isinstance(documented, dict):
        return False
    if not claimed:
        return True
    for key, claimed_value in claimed.items():
        if key not in documented:
            return False
        documented_value = documented[key]
        if isinstance(claimed_value, dict):
            if not terms_match(claimed_value, documented_value):
                return False
        elif isinstance(claimed_value, list):
            if not isinstance(documented_value, list) or len(claimed_value) != len(documented_value):
                return False
            if [normalize(v) for v in claimed_value] != [normalize(v) for v in documented_value]:
                return False
        elif normalize(claimed_value) != normalize(documented_value):
            return False
    return True


def assess(payload: Dict[str, Any]) -> Dict[str, Any]:
    card_name = payload.get("card_name")
    if not isinstance(card_name, str) or not card_name.strip():
        raise ValueError("card_name must be a non-empty string")

    documented_program = payload.get("documented_program")
    automatic_rejection = payload.get("automatic_rejection", False)
    if not isinstance(documented_program, bool):
        raise ValueError("documented_program must be a boolean")
    if not isinstance(automatic_rejection, bool):
        raise ValueError("automatic_rejection must be a boolean")

    card = card_name.strip()
    if not documented_program:
        return {
            "tool_permitted": False,
            "decision": "refuse_no_documented_program",
            "term_match": False,
            "message": (
                f"I can’t provide a referral link for {card} because an active, "
                "card-specific referral program could not be confirmed from the "
                "available documentation."
            ),
        }

    match = terms_match(payload.get("claimed_terms"), payload.get("documented_terms"))
    if not match:
        return {
            "tool_permitted": False,
            "decision": "refuse_terms_do_not_match",
            "term_match": False,
            "message": (
                f"I can’t provide a referral link for {card} because the stated "
                "offer terms do not match the documented referral program. Please "
                "use the documented terms for this card."
            ),
        }

    if automatic_rejection:
        reason = payload.get("rejection_reason")
        suffix = f" Reason: {reason.strip()}" if isinstance(reason, str) and reason.strip() else ""
        return {
            "tool_permitted": False,
            "decision": "refuse_automatic_rejection",
            "term_match": True,
            "message": (
                "I can’t provide a referral link because this referral would be "
                f"automatically denied.{suffix}"
            ),
        }

    return {
        "tool_permitted": True,
        "decision": "provide_self_service_tool",
        "term_match": True,
        "message": (
            f"The documented referral program for {card} can be used. You may offer "
            "the customer the self-service get_referral_link tool; they must supply "
            "their own user_id and this exact card name."
        ),
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(assess(payload), ensure_ascii=False))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
