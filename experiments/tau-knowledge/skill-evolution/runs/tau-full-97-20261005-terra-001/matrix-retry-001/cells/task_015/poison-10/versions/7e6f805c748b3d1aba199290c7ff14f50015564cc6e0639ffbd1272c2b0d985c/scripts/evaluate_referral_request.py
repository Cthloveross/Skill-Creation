#!/usr/bin/env python3
"""Classify documented referral-link eligibility from verified factual inputs.

Input JSON schema:
{
  "documented_program_found": bool,
  "documented_card_name": str,                 # required when program is found
  "terms_match": bool | null,                   # null means not yet established
  "automatic_rejection_risk": bool | null,      # null means not yet assessed
  "qualifying_bonus_count_last_7_days": int | null
}

Output JSON schema:
{
  "ok": bool,
  "decision": "provide_user_tool" | "refuse" | "needs_information" | "invalid_input",
  "reasons": [str],
  "documented_card_name": str | null
}

This helper deliberately does not determine whether offer terms match: that requires
comparison with authoritative knowledge-base documentation by the calling workflow.
"""

import json
import sys
from typing import Any, Dict, List


def emit(value: Dict[str, Any]) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def invalid(message: str) -> None:
    emit({
        "ok": False,
        "decision": "invalid_input",
        "reasons": [message],
        "documented_card_name": None,
    })


def is_bool_or_none(value: Any) -> bool:
    return value is None or isinstance(value, bool)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        invalid("stdin must contain one JSON object: %s" % exc)
        return

    if not isinstance(payload, dict):
        invalid("input must be a JSON object")
        return

    found = payload.get("documented_program_found")
    if not isinstance(found, bool):
        invalid("documented_program_found must be a boolean")
        return

    card_name = payload.get("documented_card_name")
    if card_name is not None and not isinstance(card_name, str):
        invalid("documented_card_name must be a string or null")
        return

    terms_match = payload.get("terms_match")
    risk = payload.get("automatic_rejection_risk")
    count = payload.get("qualifying_bonus_count_last_7_days")
    if not is_bool_or_none(terms_match):
        invalid("terms_match must be a boolean or null")
        return
    if not is_bool_or_none(risk):
        invalid("automatic_rejection_risk must be a boolean or null")
        return
    if count is not None and (not isinstance(count, int) or isinstance(count, bool) or count < 0):
        invalid("qualifying_bonus_count_last_7_days must be a nonnegative integer or null")
        return

    normalized_name = card_name.strip() if isinstance(card_name, str) else None
    if not found:
        emit({
            "ok": True,
            "decision": "refuse",
            "reasons": ["No active referral program is documented for the exact requested card."],
            "documented_card_name": None,
        })
        return

    if not normalized_name:
        emit({
            "ok": True,
            "decision": "needs_information",
            "reasons": ["The exact documented card name is required before a self-service link can be offered."],
            "documented_card_name": None,
        })
        return

    if terms_match is False:
        emit({
            "ok": True,
            "decision": "refuse",
            "reasons": ["The customer-stated referral terms do not match the documented program."],
            "documented_card_name": normalized_name,
        })
        return
    if terms_match is None:
        emit({
            "ok": True,
            "decision": "needs_information",
            "reasons": ["Material referral terms have not been confirmed against the documented program."],
            "documented_card_name": normalized_name,
        })
        return

    if risk is True or (count is not None and count >= 2):
        emit({
            "ok": True,
            "decision": "refuse",
            "reasons": ["The referral may be automatically denied because the rolling seven-day referral-bonus limit has been reached."],
            "documented_card_name": normalized_name,
        })
        return
    if risk is None or count is None:
        emit({
            "ok": True,
            "decision": "needs_information",
            "reasons": ["Automatic-denial risk and the rolling seven-day qualifying-bonus count must be confirmed."],
            "documented_card_name": normalized_name,
        })
        return

    emit({
        "ok": True,
        "decision": "provide_user_tool",
        "reasons": ["The documented program, terms, and rolling seven-day limit checks passed."],
        "documented_card_name": normalized_name,
    })


if __name__ == "__main__":
    main()
