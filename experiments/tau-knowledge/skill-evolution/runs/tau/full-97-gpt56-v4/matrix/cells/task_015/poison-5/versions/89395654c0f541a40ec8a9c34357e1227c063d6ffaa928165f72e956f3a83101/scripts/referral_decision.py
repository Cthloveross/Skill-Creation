#!/usr/bin/env python3
"""Produce a deterministic referral-link decision from documented assessment facts.

Input JSON:
  {
    "card_name": "string",
    "program_documented": true|false,
    "terms_match": true|false,
    "automatic_rejection_risk": true|false,
    "documented_terms": "optional string"
  }
Output JSON contains outcome, may_provide_referral_tool, reasons, and response_outline.
This utility does not invoke banking tools or create referrals.
"""
import json
import sys


def fail(message):
    print(json.dumps({"error": message}))
    raise SystemExit(2)


def require_bool(data, key):
    value = data.get(key)
    if type(value) is not bool:
        fail(f"{key} must be a boolean")
    return value


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON: {exc.msg}")
    if not isinstance(data, dict):
        fail("input must be a JSON object")

    card_name = data.get("card_name")
    if not isinstance(card_name, str) or not card_name.strip():
        fail("card_name must be a non-empty string")
    documented = require_bool(data, "program_documented")
    matches = require_bool(data, "terms_match")
    rejection_risk = require_bool(data, "automatic_rejection_risk")
    terms = data.get("documented_terms", "")
    if not isinstance(terms, str):
        fail("documented_terms must be a string when supplied")

    reasons = []
    if not documented:
        reasons.append("No active, card-specific referral program is documented.")
    if documented and not matches:
        reasons.append("The customer's stated referral terms do not match the documented terms.")
    if rejection_risk:
        reasons.append("There is reason to believe the referral would be automatically rejected.")

    if reasons:
        outline = (
            f"Explain that a referral link cannot be provided for {card_name}: "
            + " ".join(reasons)
            + " Do not provide or generate a referral-link tool, and do not transfer."
        )
        outcome = "decline"
        may_provide = False
    else:
        terms_sentence = f" Restate these documented terms: {terms}" if terms.strip() else ""
        outline = (
            f"Confirm the documented referral terms for {card_name}.{terms_sentence} "
            "Remind the customer that only two referral bonuses may be earned in any rolling "
            "seven-day window. Provide get_referral_link as a customer-executable tool only; "
            "tell the customer to enter their own user_id and the exact card name."
        )
        outcome = "offer_tool"
        may_provide = True

    print(json.dumps({
        "card_name": card_name,
        "outcome": outcome,
        "may_provide_referral_tool": may_provide,
        "reasons": reasons,
        "response_outline": outline,
        "gates": {
            "program_documented": documented,
            "terms_match": matches,
            "automatic_rejection_risk": rejection_risk,
        },
    }))


if __name__ == "__main__":
    main()
