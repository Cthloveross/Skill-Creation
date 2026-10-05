#!/usr/bin/env python3
"""Fail-closed assessment of documented card-referral eligibility.

Reads one JSON object from stdin and writes one JSON result to stdout. No external
files, network access, or banking actions are used.
"""

import json
import re
import sys
import unicodedata
from typing import Any, Dict, List, Optional


def normalize(value: Any) -> str:
    """Normalize case, Unicode punctuation, and spacing for deterministic matching."""
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKD", value).casefold()
    text = text.translate(str.maketrans({
        "’": "'", "‘": "'", "‛": "'", "`": "'",
        "“": '"', "”": '"', "„": '"',
        "–": "-", "—": "-", "−": "-",
    }))
    return re.sub(r"[^a-z0-9]+", "", text)


def result(
    decision: str,
    reason_code: str,
    matched_program: Optional[Dict[str, str]],
    customer_message: str,
) -> Dict[str, Any]:
    return {
        "decision": decision,
        "reason_code": reason_code,
        "matched_program": matched_program,
        "customer_message": customer_message,
    }


def assess(payload: Dict[str, Any]) -> Dict[str, Any]:
    card_name = payload.get("requested_card_name")
    programs = payload.get("documented_programs", [])
    claimed_terms = payload.get("customer_claimed_terms")

    if not isinstance(card_name, str) or not card_name.strip():
        return result(
            "do_not_offer_link",
            "no_documented_card_program",
            None,
            "I cannot confirm a documented referral program because the card name is missing, so I cannot provide a referral link.",
        )
    if not isinstance(programs, list):
        programs = []

    target = normalize(card_name)
    card_records: List[Dict[str, Any]] = [
        record for record in programs
        if isinstance(record, dict) and normalize(record.get("card_name")) == target
    ]
    if not card_records:
        return result(
            "do_not_offer_link",
            "no_documented_card_program",
            None,
            "I cannot confirm a documented referral program for that specific card, so I cannot provide a referral link.",
        )

    active_records = [record for record in card_records if record.get("active") is True]
    if not active_records:
        return result(
            "do_not_offer_link",
            "inactive_card_program",
            None,
            "I cannot confirm a documented active referral program for that card, so I cannot provide a referral link.",
        )

    distinct_terms = {normalize(record.get("terms")) for record in active_records}
    if len(active_records) != 1 or len(distinct_terms) != 1 or "" in distinct_terms:
        return result(
            "do_not_offer_link",
            "ambiguous_card_documentation",
            None,
            "I cannot confirm one clear documented referral offer for that card, so I cannot provide a referral link.",
        )

    program = active_records[0]
    documented_terms = program.get("terms")
    if not isinstance(documented_terms, str) or not documented_terms.strip():
        return result(
            "do_not_offer_link",
            "ambiguous_card_documentation",
            None,
            "I cannot confirm the documented terms for that card's referral offer, so I cannot provide a referral link.",
        )

    if claimed_terms is not None:
        if (
            not isinstance(claimed_terms, str)
            or not claimed_terms.strip()
            or normalize(claimed_terms) != normalize(documented_terms)
        ):
            return result(
                "do_not_offer_link",
                "claimed_terms_mismatch",
                None,
                "I cannot confirm that the referral terms provided match the documented offer for that card, so I cannot provide a referral link.",
            )

    matched = {"card_name": program["card_name"], "terms": documented_terms}
    return result(
        "offer_link",
        "documented_active_offer",
        matched,
        "The documented referral offer is confirmed. You can generate a referral link yourself using your user ID and the exact card name. Referral bonuses are limited to two successful referrals in any rolling seven-day window; additional referrals in that window are automatically denied.",
    )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object")
        output = assess(payload)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        output = result(
            "do_not_offer_link",
            "no_documented_card_program",
            None,
            "I cannot confirm a documented referral program from the available information, so I cannot provide a referral link.",
        )
        output["input_error"] = str(exc)
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
