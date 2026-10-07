#!/usr/bin/env python3
"""Assess documented credit-card referral-offer eligibility.

Reads one JSON object from stdin and writes one JSON assessment to stdout.
No external dependencies, files, account data, or tools are used.
"""

import json
import sys
from typing import Any, Dict, List, Tuple


def norm_card(value: str) -> str:
    """Case/whitespace-insensitive lookup while retaining canonical output."""
    return " ".join(value.casefold().split())


def canonical(value: Any) -> Any:
    """Make JSON values comparable irrespective of object-key ordering."""
    if isinstance(value, dict):
        return {str(k): canonical(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return [canonical(v) for v in value]
    return value


def error(message: str) -> Dict[str, Any]:
    return {
        "decision": "refuse",
        "reasons": ["invalid_input", message],
        "card_name": None,
        "documented_terms": None,
    }


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    card_name = payload.get("card_name")
    if not isinstance(card_name, str) or not card_name.strip():
        return error("card_name must be a nonempty string")

    offers = payload.get("documented_offers")
    if not isinstance(offers, list):
        return error("documented_offers must be an array of authoritative search results")

    claimed = payload.get("claimed_terms", None)
    if claimed is not None and not isinstance(claimed, dict):
        return error("claimed_terms must be an object or null")

    count = payload.get("completed_bonus_count_last_7_days")
    if count is not None and (not isinstance(count, int) or isinstance(count, bool) or count < 0):
        return error("completed_bonus_count_last_7_days must be a nonnegative integer when supplied")

    matching: List[Dict[str, Any]] = []
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        offer_card = offer.get("card_name")
        if isinstance(offer_card, str) and norm_card(offer_card) == norm_card(card_name):
            matching.append(offer)

    documented_active = [
        offer for offer in matching
        if offer.get("documented") is True and offer.get("active") is True
    ]

    base = {"card_name": None, "documented_terms": None}
    if not documented_active:
        return {
            "decision": "refuse",
            "reasons": ["no_documented_active_offer_for_requested_card"],
            **base,
        }

    # Multiple active records can be safely used only if their canonical offer data agree.
    signatures: List[Tuple[Any, Any]] = [
        (offer.get("card_name"), canonical(offer.get("terms"))) for offer in documented_active
    ]
    if len({json.dumps(sig, sort_keys=True) for sig in signatures}) != 1:
        return {
            "decision": "refuse",
            "reasons": ["ambiguous_documented_offer"],
            **base,
        }

    offer = documented_active[0]
    terms = offer.get("terms")
    canonical_card = offer["card_name"]
    if terms is not None and not isinstance(terms, dict):
        return {
            "decision": "refuse",
            "reasons": ["invalid_documented_terms"],
            "card_name": canonical_card,
            "documented_terms": None,
        }

    if claimed is not None:
        # A quoted term must be explicitly documented and equal, including its unit/timeframe.
        if terms is None or any(
            key not in terms or canonical(terms[key]) != canonical(value)
            for key, value in claimed.items()
        ):
            return {
                "decision": "refuse",
                "reasons": ["claimed_terms_do_not_match_documented_offer"],
                "card_name": canonical_card,
                "documented_terms": terms,
            }

    denial_reasons: List[str] = []
    if payload.get("automatic_rejection_likely") is True:
        denial_reasons.append("automatic_rejection_likely")
    if count is not None and count >= 2:
        denial_reasons.append("weekly_referral_bonus_limit_reached")
    if denial_reasons:
        return {
            "decision": "refuse",
            "reasons": denial_reasons,
            "card_name": canonical_card,
            "documented_terms": terms,
        }

    return {
        "decision": "provide_user_tool",
        "reasons": ["specific_active_offer_and_terms_confirmed"],
        "card_name": canonical_card,
        "documented_terms": terms,
        "user_tool": "get_referral_link",
        "user_tool_signature": "get_referral_link(user_id: str, card_name: str)",
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            result = error("top-level JSON value must be an object")
        else:
            result = main(raw)
    except json.JSONDecodeError:
        result = error("stdin must contain valid JSON")
    except Exception as exc:  # Keep malformed evidence fail-closed.
        result = error("unable to assess offer: " + str(exc))
    print(json.dumps(result, sort_keys=True))
