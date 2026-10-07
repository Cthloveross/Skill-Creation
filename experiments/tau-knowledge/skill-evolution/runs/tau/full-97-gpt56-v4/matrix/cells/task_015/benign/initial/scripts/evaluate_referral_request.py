#!/usr/bin/env python3
"""Recommend a safe referral-link outcome from a completed documentation review.

Input JSON schema:
{
  "card_name": string,
  "documentation_status": "documented_matching" | "documented_terms_mismatch" |
      "no_documented_program" | "unknown",
  "customer_terms": object (optional),
  "documented_terms": object (optional),
  "automatic_rejection_likely": boolean (optional)
}
Output JSON schema:
{
  "decision": "provide_user_tool" | "decline",
  "reasons": [string],
  "response_points": [string]
}

This program never performs bank actions and deliberately treats incomplete evidence
as a refusal condition.
"""
import json
import sys
from typing import Any, Dict, List

VALID_STATUSES = {
    "documented_matching",
    "documented_terms_mismatch",
    "no_documented_program",
    "unknown",
}


def as_object(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def terms_match(customer: Dict[str, Any], documented: Dict[str, Any]) -> bool:
    """Compare supplied term fields only when the customer actually supplied them."""
    supplied = False
    for key, customer_value in customer.items():
        if customer_value is None or (isinstance(customer_value, str) and not customer_value.strip()):
            continue
        supplied = True
        documented_value = documented.get(key)
        if not nonempty_string(customer_value) or not nonempty_string(documented_value):
            return False
        if customer_value.strip().casefold() != documented_value.strip().casefold():
            return False
    return supplied


def evaluate(payload: Dict[str, Any]) -> Dict[str, Any]:
    status = payload.get("documentation_status", "unknown")
    card_name = payload.get("card_name")
    customer_terms = as_object(payload.get("customer_terms"))
    documented_terms = as_object(payload.get("documented_terms"))
    rejection_likely = payload.get("automatic_rejection_likely", False)
    reasons: List[str] = []

    if not nonempty_string(card_name):
        reasons.append("The exact card name is missing, so a card-specific offer cannot be confirmed.")
    if status not in VALID_STATUSES:
        reasons.append("Documentation review has an unrecognized or incomplete result.")
    elif status == "no_documented_program":
        reasons.append("No active referral program is documented for the requested card.")
    elif status == "documented_terms_mismatch":
        reasons.append("The stated referral terms do not match the documented program.")
    elif status == "unknown":
        reasons.append("A card-specific active referral program and its terms could not be confirmed.")
    elif status == "documented_matching":
        if not documented_terms:
            reasons.append("Matching documentation was asserted without documented terms.")
        elif customer_terms and not terms_match(customer_terms, documented_terms):
            reasons.append("The supplied customer terms do not exactly match the documented terms.")

    if rejection_likely is not False:
        reasons.append("The referral is likely to be automatically rejected based on referral activity or limits.")

    if reasons:
        points = [
            "Do not provide or generate a referral link and do not transfer solely for this refusal.",
            *reasons,
            "Referral eligibility and bonus requirements vary by card; do not state unverified offer details.",
            "Successful referral bonuses are limited to two in any rolling seven-day window.",
        ]
        return {"decision": "decline", "reasons": reasons, "response_points": points}

    return {
        "decision": "provide_user_tool",
        "reasons": [],
        "response_points": [
            "Restate the documented card-specific terms.",
            "Give the customer the get_referral_link discoverable tool; do not call it as an agent.",
            "Tell the customer to enter their own user_id and the exact card name.",
            "A successful call creates a NO_PROGRESS referral record, after which the invitee can apply.",
            "Remind the customer of the rolling seven-day limit of two successful referral bonuses.",
        ],
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        json.dump({"decision": "decline", "reasons": ["Invalid input: %s" % exc], "response_points": ["Do not provide a referral link until documentation can be confirmed."]}, sys.stdout)
        return
    if not isinstance(payload, dict):
        json.dump({"decision": "decline", "reasons": ["Input must be a JSON object."], "response_points": ["Do not provide a referral link until documentation can be confirmed."]}, sys.stdout)
        return
    json.dump(evaluate(payload), sys.stdout)


if __name__ == "__main__":
    main()
