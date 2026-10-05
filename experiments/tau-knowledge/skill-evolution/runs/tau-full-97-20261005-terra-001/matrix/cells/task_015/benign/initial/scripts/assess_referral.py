#!/usr/bin/env python3
"""Safely assess whether a customer-run referral-link tool may be exposed.

Input and output are JSON objects on stdin/stdout.  This program is advisory only:
it does not access accounts, determine undocumented offers, or invoke banking tools.
"""

import json
import sys
from typing import Any, Dict, List, Optional


def canonical(value: Any) -> Any:
    """Return a JSON-comparable canonical form without changing semantic values."""
    if isinstance(value, dict):
        return {str(key): canonical(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, list):
        return [canonical(item) for item in value]
    return value


def normalized_name(value: str) -> str:
    return " ".join(value.casefold().split())


def result(
    decision: str,
    reasons: List[str],
    exact_card_name: Optional[str] = None,
    documented_terms: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "decision": decision,
        "provide_user_tool": decision == "eligible_to_offer_tool",
        "exact_card_name": exact_card_name,
        "documented_terms": documented_terms,
        "reasons": reasons,
    }


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    requested = payload.get("requested_card_name")
    offers = payload.get("documented_offers")
    claimed = payload.get("claimed_terms", None)
    referral_count = payload.get("rolling_7_day_successful_referrals", None)

    if not isinstance(requested, str) or not requested.strip() or not isinstance(offers, list):
        return result("invalid_input", ["requested_card_name and documented_offers are required"])
    if claimed is not None and not isinstance(claimed, dict):
        return result("invalid_input", ["claimed_terms must be an object or null"])
    if referral_count is not None and (
        not isinstance(referral_count, int)
        or isinstance(referral_count, bool)
        or referral_count < 0
    ):
        return result("invalid_input", ["rolling_7_day_successful_referrals must be a nonnegative integer"])

    matches: List[Dict[str, Any]] = []
    requested_normalized = normalized_name(requested)
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        card_name = offer.get("card_name")
        if isinstance(card_name, str) and normalized_name(card_name) == requested_normalized:
            matches.append(offer)

    active_matches = [
        offer for offer in matches
        if offer.get("active") is True and isinstance(offer.get("terms"), dict)
    ]
    if len(active_matches) != 1:
        return result(
            "no_documented_active_program",
            ["no single active card-specific documented offer was supplied"],
        )

    offer = active_matches[0]
    exact_name = offer["card_name"]
    terms = offer["terms"]

    if claimed is None:
        return result(
            "term_confirmation_needed",
            ["customer has not confirmed the documented referral terms"],
            exact_name,
            terms,
        )

    if canonical(claimed) != canonical(terms):
        return result(
            "terms_do_not_match",
            ["customer-stated terms do not exactly match the documented card-specific terms"],
            exact_name,
            terms,
        )

    if referral_count is not None and referral_count >= 2:
        return result(
            "automatic_denial_risk",
            ["two or more successful referral bonuses are already recorded in the rolling seven-day window"],
            exact_name,
            terms,
        )

    return result(
        "eligible_to_offer_tool",
        ["active card-specific program and matching terms are documented"],
        exact_name,
        terms,
    )


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps(result("invalid_input", [str(exc)]), sort_keys=True))
