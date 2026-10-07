#!/usr/bin/env python3
"""Deterministically assess whether a referral-link tool may be offered.

Reads a JSON object from stdin and writes a JSON decision object to stdout.
This script is advisory: it performs no bank action and never creates a link.
"""

import json
import sys
from typing import Any, Dict, List


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def normalized(value: Any) -> str:
    return " ".join(text(value).casefold().split())


def terms_match(claimed: Dict[str, Any], documented: Dict[str, Any]) -> bool:
    """Require every customer-provided material term to equal a documented term."""
    for field in ("bonus", "qualifying_requirement", "timeframe"):
        customer_value = normalized(claimed.get(field))
        documented_value = normalized(documented.get(field))
        if customer_value and (not documented_value or customer_value != documented_value):
            return False
    return True


def documented_summary(documented: Dict[str, Any]) -> str:
    pieces: List[str] = []
    labels = {
        "bonus": "bonus",
        "qualifying_requirement": "qualifying requirement",
        "timeframe": "timeframe",
    }
    for key in ("bonus", "qualifying_requirement", "timeframe"):
        value = text(documented.get(key))
        if value:
            pieces.append(f"{labels[key]}: {value}")
    return "; ".join(pieces)


def assess(payload: Dict[str, Any]) -> Dict[str, Any]:
    card_name = text(payload.get("card_name"))
    claimed = payload.get("claimed_terms") or {}
    documented = payload.get("documented_terms") or {}
    program_found = payload.get("documented_program_found") is True
    active_offer = payload.get("active_offer") is True
    rejection_reason = text(payload.get("automatic_rejection_reason"))

    if not card_name:
        return {
            "decision": "need_card_or_terms",
            "give_referral_tool": False,
            "transfer_to_human": False,
            "reason": "The exact card name is required to locate card-specific referral documentation.",
            "customer_guidance": "Please provide the exact name of the card for the referral offer so its current terms can be checked.",
        }

    if rejection_reason:
        return {
            "decision": "decline_auto_rejection",
            "give_referral_tool": False,
            "transfer_to_human": False,
            "reason": rejection_reason,
            "customer_guidance": (
                f"A referral link cannot be provided for {card_name} because: {rejection_reason}"
            ),
        }

    if not program_found or not active_offer:
        return {
            "decision": "decline_no_documented_program",
            "give_referral_tool": False,
            "transfer_to_human": False,
            "reason": "No active, card-specific documented referral program was confirmed.",
            "customer_guidance": (
                f"I cannot confirm an active documented referral program for {card_name}, "
                "so I cannot provide a referral link."
            ),
        }

    if not terms_match(claimed, documented):
        summary = documented_summary(documented)
        guidance = (
            f"I cannot provide a referral link because the stated terms for {card_name} "
            "do not match the documented referral offer."
        )
        if summary:
            guidance += f" Documented terms: {summary}."
        return {
            "decision": "decline_terms_mismatch",
            "give_referral_tool": False,
            "transfer_to_human": False,
            "reason": "One or more claimed material terms differ from, or are absent from, the documented program.",
            "customer_guidance": guidance,
        }

    summary = documented_summary(documented)
    guidance = (
        f"The referral offer for {card_name} is documented and its terms have been confirmed. "
        "Please run get_referral_link yourself using your own user ID and the exact card name. "
        "A successful call creates a NO_PROGRESS referral record. Referral bonuses are limited "
        "to two successful bonuses in any rolling seven-day window across card types."
    )
    if summary:
        guidance = f"Documented terms: {summary}. " + guidance
    return {
        "decision": "provide_link_tool",
        "give_referral_tool": True,
        "transfer_to_human": False,
        "reason": "An active card-specific program is documented and all claimed material terms match.",
        "customer_guidance": guidance,
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(assess(payload), ensure_ascii=False))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({
            "decision": "need_card_or_terms",
            "give_referral_tool": False,
            "transfer_to_human": False,
            "reason": f"Invalid assessment input: {exc}",
            "customer_guidance": "I need the exact card name and documented referral-offer details before a referral link can be considered.",
        }))


if __name__ == "__main__":
    main()
