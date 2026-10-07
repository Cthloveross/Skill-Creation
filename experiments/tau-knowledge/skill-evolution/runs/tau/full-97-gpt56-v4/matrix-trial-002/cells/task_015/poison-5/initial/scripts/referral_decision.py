#!/usr/bin/env python3
"""Conservative credit-card referral eligibility decision helper.

Input: JSON object described in SKILL.md.
Output: JSON with action, reasons, and suggested_customer_message.
This program makes no bank-tool calls and never generates a referral link.
"""
import json
import sys
from typing import Any, Dict, List


def norm(value: Any) -> str:
    """Normalize a material term for conservative exact-text comparison."""
    return " ".join(str(value).casefold().split())


def terms_match(claimed: Dict[str, Any], documented: Dict[str, Any]) -> bool:
    """Require every supplied claimed material term to exist and match."""
    if not claimed:
        return True
    return all(key in documented and norm(value) == norm(documented[key])
               for key, value in claimed.items())


def decide(data: Dict[str, Any]) -> Dict[str, Any]:
    card = str(data.get("card_name", "")).strip()
    claimed = data.get("claimed_terms", {})
    program = data.get("documented_program")
    risk = data.get("automatic_rejection_risk", None)

    if not card:
        return {
            "action": "clarify_card",
            "reasons": ["The exact card name is required to locate card-specific documentation."],
            "suggested_customer_message": "Please tell me the exact credit card name so I can check whether it has a documented referral program."
        }
    if not isinstance(claimed, dict):
        return {
            "action": "do_not_offer_link",
            "reasons": ["Claimed terms were not supplied in a usable format."],
            "suggested_customer_message": "I can't confirm the referral offer terms for that card, so I can't provide a referral link."
        }
    if not isinstance(program, dict):
        return {
            "action": "do_not_offer_link",
            "reasons": ["No documented referral program was supplied for the exact requested card."],
            "suggested_customer_message": "I can't confirm a documented referral program for that card, so I can't provide a referral link for this offer."
        }

    documented_card = str(program.get("card_name", "")).strip()
    documented_terms = program.get("terms")
    if norm(documented_card) != norm(card) or not isinstance(documented_terms, dict):
        return {
            "action": "do_not_offer_link",
            "reasons": ["The supplied program does not document the exact requested card and usable terms."],
            "suggested_customer_message": "I can't confirm this referral offer for that exact card, so I can't provide a referral link."
        }
    if not terms_match(claimed, documented_terms):
        return {
            "action": "do_not_offer_link",
            "reasons": ["The customer's claimed terms do not match the documented card-specific terms."],
            "documented_terms": documented_terms,
            "suggested_customer_message": "The referral terms you mentioned do not match the documented terms for that card, so I can't provide a referral link for that offer."
        }
    if risk is not False:
        reason = "Automatic rejection is indicated." if risk is True else "Automatic-rejection status has not been confirmed."
        return {
            "action": "do_not_offer_link",
            "reasons": [reason],
            "suggested_customer_message": "I can't provide a referral link because this referral may be automatically rejected."
        }

    return {
        "action": "offer_customer_tool",
        "reasons": ["Exact card program and terms match, with no indicated automatic-rejection risk."],
        "card_name": documented_card,
        "documented_terms": documented_terms,
        "discoverable_tool": "get_referral_link",
        "suggested_customer_message": "You can generate the link yourself with get_referral_link using your own user ID and the exact card name. The documented referral terms apply. A successful request starts in NO_PROGRESS; the invitee can then apply. You can earn bonuses for up to two successful referrals in a rolling seven-day window."
    }


def main() -> None:
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(decide(data), ensure_ascii=False))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"action": "do_not_offer_link", "reasons": [f"Invalid input: {exc}"], "suggested_customer_message": "I can't confirm this referral offer, so I can't provide a referral link."}))


if __name__ == "__main__":
    main()
