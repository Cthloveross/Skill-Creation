#!/usr/bin/env python3
"""Deterministically compare evidence-extracted credit-card records.

Reads one JSON object from stdin.  See SKILL.md for the input schema.
Writes a JSON object to stdout; it does not access accounts, files, or networks.
"""
import json
import sys
from typing import Any, Dict, List, Optional


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def num_or_none(value: Any) -> Optional[float]:
    return float(value) if is_number(value) else None


def check_equal_number(actual: Any, expected: Any) -> Optional[bool]:
    if expected is None:
        return None
    if not is_number(actual) or not is_number(expected):
        return False
    return float(actual) == float(expected)


def check_minimum(actual: Any, minimum: Any) -> Optional[bool]:
    if minimum is None:
        return None
    if not is_number(actual) or not is_number(minimum):
        return False
    return float(actual) >= float(minimum)


def reward_for_priority(card: Dict[str, Any], priority: str) -> Optional[float]:
    rewards = card.get("rewards")
    if not isinstance(rewards, dict):
        return None
    key = "travel_percent" if priority == "travel" else "general_percent"
    return num_or_none(rewards.get(key))


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"validation_errors": ["Input is not valid JSON: " + str(exc)]}))
        return

    errors: List[str] = []
    if not isinstance(data, dict):
        print(json.dumps({"validation_errors": ["Top-level input must be an object."]}))
        return
    requirements = data.get("requirements", {})
    cards = data.get("cards", [])
    if not isinstance(requirements, dict):
        errors.append("requirements must be an object.")
        requirements = {}
    if not isinstance(cards, list):
        errors.append("cards must be an array.")
        cards = []

    priority = requirements.get("spending_priority", "none")
    if priority is None:
        priority = "none"
    if priority not in ("travel", "general", "none"):
        errors.append("spending_priority must be travel, general, none, or null.")
        priority = "none"

    requested_fee = requirements.get("foreign_transaction_fee_percent")
    requested_limit = requirements.get("minimum_possible_credit_limit")
    requested_protection = requirements.get("purchase_protection_required")
    if requested_protection is not None and not isinstance(requested_protection, bool):
        errors.append("purchase_protection_required must be true, false, or null.")

    results: List[Dict[str, Any]] = []
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            errors.append("cards[%d] must be an object." % index)
            continue
        name = card.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append("cards[%d].name must be a nonempty string." % index)
            name = "Unnamed card %d" % (index + 1)

        checks: Dict[str, Optional[bool]] = {
            "foreign_transaction_fee": check_equal_number(
                card.get("foreign_transaction_fee_percent"), requested_fee
            ),
            "possible_credit_limit": check_minimum(
                card.get("typical_limit_max"), requested_limit
            ),
            "purchase_protection": (
                None if requested_protection is None
                else card.get("purchase_protection_available") is True
                if requested_protection else True
            ),
        }
        required_checks = [value for value in checks.values() if value is not None]
        eligible = all(value is True for value in required_checks)
        unmet = [key for key, value in checks.items() if value is False]

        priority_rate = reward_for_priority(card, priority) if priority != "none" else None
        # Ranking is descriptive and deterministic: preference reward rate first,
        # then documented protection duration/cap and published maximum limit.
        # Missing values sort below documented values without being treated as zero facts.
        rank_key = [
            -(priority_rate if priority_rate is not None else -1),
            -(num_or_none(card.get("purchase_protection_days")) or -1),
            -(num_or_none(card.get("purchase_protection_max_per_claim")) or -1),
            -(num_or_none(card.get("typical_limit_max")) or -1),
            str(name).casefold(),
        ]
        results.append({
            "name": name,
            "audience": card.get("audience"),
            "eligible": eligible,
            "requirement_checks": checks,
            "unmet_requirements": unmet,
            "priority": priority,
            "priority_reward_percent": priority_rate,
            "facts": {
                "typical_limit_min": card.get("typical_limit_min"),
                "typical_limit_max": card.get("typical_limit_max"),
                "foreign_transaction_fee_percent": card.get("foreign_transaction_fee_percent"),
                "purchase_protection_available": card.get("purchase_protection_available"),
                "purchase_protection_days": card.get("purchase_protection_days"),
                "purchase_protection_max_per_claim": card.get("purchase_protection_max_per_claim"),
                "annual_fee": card.get("annual_fee"),
                "rewards": card.get("rewards"),
            },
            "eligibility_notes": card.get("eligibility_notes", []),
            "caveats": card.get("caveats", []),
            "sources": card.get("sources", []),
            "_rank_key": rank_key,
        })

    eligible = [item for item in results if item["eligible"]]
    eligible.sort(key=lambda item: item["_rank_key"])
    for item in results:
        item.pop("_rank_key", None)
    for item in eligible:
        item.pop("_rank_key", None)

    output = {
        "validation_errors": errors,
        "requirements_used": {
            "foreign_transaction_fee_percent": requested_fee,
            "minimum_possible_credit_limit": requested_limit,
            "purchase_protection_required": requested_protection,
            "spending_priority": priority,
        },
        "cards": results,
        "eligible_ranked": eligible,
        "recommendation_available": len(eligible) > 0 and len(errors) == 0,
        "method_note": (
            "Eligibility requires every supplied hard requirement to be documented as met. "
            "Ranking uses the stated spending-priority reward rate, then documented protection "
            "duration, protection cap, and typical/published maximum limit."
        ),
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
