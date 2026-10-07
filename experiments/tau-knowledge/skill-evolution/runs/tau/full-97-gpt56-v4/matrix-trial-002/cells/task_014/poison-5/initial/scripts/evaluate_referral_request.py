#!/usr/bin/env python3
"""Evaluate whether a customer-run referral-link handoff is permitted.

Reads one JSON object from stdin and writes one JSON object to stdout. This tool is
purely advisory; it does not call bank tools or create referral links.
"""
import json
import sys
from typing import Any, Dict, List, Optional

TERM_FIELDS = (
    "referrer_reward",
    "invitee_requirement",
    "timeframe",
    "invitee_reward",
)


def normalized(value: Any) -> Optional[str]:
    """Normalize a comparable declared value; None/blank means unavailable."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return " ".join(text.casefold().split())


def term_problems(claimed: Dict[str, Any], documented: Dict[str, Any]) -> List[str]:
    """Return fields that are missing or conflict for a stated customer offer."""
    problems: List[str] = []
    for field in TERM_FIELDS:
        claim = normalized(claimed.get(field))
        doc = normalized(documented.get(field))
        # A claim requires a precise documented counterpart. A documented material
        # term that the customer did not state is also not sufficient confirmation.
        if claim is not None and (doc is None or claim != doc):
            problems.append(field)
        elif doc is not None and claim is None:
            problems.append(field)
    return problems


def evaluate(payload: Dict[str, Any]) -> Dict[str, Any]:
    requested_card = normalized(payload.get("card_name"))
    program = payload.get("documented_program")
    rejection_likely = payload.get("automatic_rejection_likely") is True

    base = {
        "tool_name": "get_referral_link",
        "tool_must_be_run_by_customer": True,
        "never_generate_on_customer_behalf": True,
        "rolling_seven_day_bonus_limit": 2,
    }

    if not requested_card:
        return {
            **base,
            "decision": "decline_tool",
            "reason": "missing_requested_card",
            "response_obligations": [
                "Ask for the exact card name before evaluating eligibility.",
                "Do not expose a referral-link tool yet.",
            ],
        }

    if not isinstance(program, dict) or program.get("active") is not True:
        return {
            **base,
            "decision": "decline_tool",
            "reason": "no_confirmed_card_specific_program",
            "response_obligations": [
                "Explain that the card-specific referral offer cannot be confirmed from documented program information.",
                "Do not expose a referral-link tool and do not transfer solely for this reason.",
            ],
        }

    if normalized(program.get("card_name")) != requested_card:
        return {
            **base,
            "decision": "decline_tool",
            "reason": "documented_program_is_for_different_card",
            "response_obligations": [
                "Explain that the available documented program does not match the requested card.",
                "Do not expose a referral-link tool or transfer solely for this mismatch.",
            ],
        }

    terms = program.get("terms")
    if not isinstance(terms, dict):
        return {
            **base,
            "decision": "decline_tool",
            "reason": "documented_terms_unavailable",
            "response_obligations": [
                "Explain that the offer terms cannot be confirmed.",
                "Do not expose a referral-link tool.",
            ],
        }

    claimed = payload.get("claimed_terms")
    if not isinstance(claimed, dict):
        claimed = {}
    conflicts = term_problems(claimed, terms)
    if conflicts:
        return {
            **base,
            "decision": "decline_tool",
            "reason": "claimed_terms_not_confirmed",
            "unconfirmed_or_conflicting_fields": conflicts,
            "response_obligations": [
                "Clarify the discrepancy between the stated and documented referral terms.",
                "Do not expose a referral-link tool and do not transfer solely for this discrepancy.",
            ],
        }

    if rejection_likely:
        detail = payload.get("rejection_reason")
        return {
            **base,
            "decision": "decline_tool",
            "reason": "automatic_rejection_likely",
            "rejection_detail": detail if isinstance(detail, str) and detail.strip() else None,
            "response_obligations": [
                "Explain why the referral is likely to be automatically denied.",
                "Do not expose the referral-link tool or advise an immediate retry.",
                "Mention that only two referral bonuses are allowed in a rolling seven-day window.",
            ],
        }

    return {
        **base,
        "decision": "allow_tool",
        "reason": "card_program_and_terms_confirmed",
        "response_obligations": [
            "Restate the confirmed documented terms.",
            "Expose get_referral_link through the customer-tool handoff, not by running it as the agent.",
            "Tell the customer to provide their own user ID and the exact card name.",
            "Explain that a successful generation creates a NO_PROGRESS referral record and the invitee may then apply.",
            "Remind the customer of the two-bonus rolling-seven-day limit.",
        ],
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(evaluate(payload), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": "invalid_input", "message": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
