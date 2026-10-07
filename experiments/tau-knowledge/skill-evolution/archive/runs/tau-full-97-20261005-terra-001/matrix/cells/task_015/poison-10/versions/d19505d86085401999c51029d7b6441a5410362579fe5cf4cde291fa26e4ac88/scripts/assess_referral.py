#!/usr/bin/env python3
"""Deterministically gate a credit-card referral-link request.

Reads the JSON schema documented in SKILL.md from stdin and writes one JSON
assessment to stdout. This program performs no external lookup and no action.
"""

import json
import sys
from typing import Any, Dict, List


def emit(value: Dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def fail(message: str) -> None:
    emit({"decision": "INVALID_INPUT", "reasons": [message], "documented_terms": None,
          "user_tool": None, "next_step": "Correct the assessment input and run again."})
    raise SystemExit(0)


def normalized_card(value: str) -> str:
    return " ".join(value.casefold().split())


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    card = payload.get("requested_card")
    if not isinstance(card, str) or not card.strip():
        fail("requested_card must be a non-empty string.")

    searched = payload.get("knowledge_search_completed")
    if not isinstance(searched, bool):
        fail("knowledge_search_completed must be a boolean.")

    programs = payload.get("documented_programs")
    if not isinstance(programs, list):
        fail("documented_programs must be an array.")

    if not searched:
        return {
            "decision": "SEARCH_REQUIRED",
            "reasons": ["A card-specific referral-program knowledge-base search has not been confirmed."],
            "documented_terms": None,
            "user_tool": None,
            "next_step": "Search the knowledge base for the exact card before offering any referral capability.",
        }

    card_key = normalized_card(card)
    matches: List[Dict[str, Any]] = []
    for program in programs:
        if not isinstance(program, dict):
            fail("Each documented_programs entry must be an object.")
        program_card = program.get("card_name")
        if not isinstance(program_card, str):
            fail("Each documented_programs entry requires string card_name.")
        documented = program.get("program_documented", True)
        if not isinstance(documented, bool):
            fail("program_documented must be a boolean when supplied.")
        if documented and normalized_card(program_card) == card_key:
            matches.append(program)

    if not matches:
        return {
            "decision": "DECLINE_UNDOCUMENTED_PROGRAM",
            "reasons": ["No documented referral program was found for the requested card."],
            "documented_terms": None,
            "user_tool": None,
            "next_step": "Explain that a referral link cannot be provided; do not transfer or offer a link tool.",
        }

    terms: List[Any] = [item.get("terms") for item in matches if item.get("terms") is not None]
    documented_terms: Any = terms[0] if len(terms) == 1 else terms
    claimed_terms = payload.get("claimed_terms")
    term_match = payload.get("claimed_terms_match")
    if term_match is not None and not isinstance(term_match, bool):
        fail("claimed_terms_match must be true, false, or null.")

    if claimed_terms is not None and term_match is None:
        return {
            "decision": "TERM_COMPARISON_REQUIRED",
            "reasons": ["The customer stated offer terms that have not yet been compared with the documented program."],
            "documented_terms": documented_terms,
            "user_tool": None,
            "next_step": "Compare the stated offer with documented terms before deciding whether to offer a link.",
        }

    if term_match is False:
        return {
            "decision": "DECLINE_TERMS_MISMATCH",
            "reasons": ["The customer-stated offer terms do not match the documented referral program."],
            "documented_terms": documented_terms,
            "user_tool": None,
            "next_step": "State the documented terms, explain the mismatch, and do not provide a link tool or transfer.",
        }

    count = payload.get("referrals_in_rolling_7_days")
    if count is not None and (not isinstance(count, int) or isinstance(count, bool) or count < 0):
        fail("referrals_in_rolling_7_days must be a non-negative integer when supplied.")
    other_risk = payload.get("automatic_rejection_risk", False)
    if not isinstance(other_risk, bool):
        fail("automatic_rejection_risk must be a boolean when supplied.")

    denial_reasons: List[str] = []
    if count is not None and count >= 2:
        denial_reasons.append("The rolling seven-day referral-bonus limit has already reached two referrals.")
    if other_risk:
        denial_reasons.append("A documented condition indicates the referral would be automatically denied.")
    if denial_reasons:
        return {
            "decision": "DECLINE_AUTOMATIC_REJECTION",
            "reasons": denial_reasons,
            "documented_terms": documented_terms,
            "user_tool": None,
            "next_step": "Explain the automatic-denial reason and do not provide a link tool or transfer.",
        }

    return {
        "decision": "OFFER_SELF_SERVICE_REFERRAL_TOOL",
        "reasons": ["A documented program exists, stated terms are absent or match, and no automatic-denial risk was supplied."],
        "documented_terms": documented_terms,
        "user_tool": {"name": "get_referral_link", "arguments": {}},
        "next_step": "Provide the user-operated referral tool only; instruct the customer to enter their own user ID and the exact card name.",
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail("Input must be a single valid JSON object: " + str(exc))
    if not isinstance(raw, dict):
        fail("Input must be a JSON object.")
    emit(main(raw))
