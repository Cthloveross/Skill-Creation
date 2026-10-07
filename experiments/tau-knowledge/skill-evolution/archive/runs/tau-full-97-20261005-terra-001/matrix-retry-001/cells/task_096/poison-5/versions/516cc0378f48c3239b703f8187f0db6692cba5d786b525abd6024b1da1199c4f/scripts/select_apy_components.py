#!/usr/bin/env python3
"""Select highest non-stacking APY components from already-screened candidates."""
import json
import sys
from decimal import Decimal, InvalidOperation

ZERO = Decimal("0")


def fail(message):
    raise ValueError(message)


def amount(value, label):
    if isinstance(value, bool):
        fail(f"{label} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        fail(f"{label} must be numeric")
    if not result.is_finite() or result < ZERO:
        fail(f"{label} must be a finite nonnegative number")
    return result


def display(value):
    """Use a compact source-like percentage representation without float artifacts."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def choose(candidates, rate_key, category):
    if not isinstance(candidates, list):
        fail(f"{category} must be a list")
    eligible = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            fail(f"{category}[{index}] must be an object")
        eligible_flag = candidate.get("eligible", False)
        if not isinstance(eligible_flag, bool):
            fail(f"{category}[{index}].eligible must be boolean")
        rate = amount(candidate.get(rate_key, 0), f"{category}[{index}].{rate_key}")
        if eligible_flag:
            name = candidate.get("source_name")
            if not isinstance(name, str) or not name.strip():
                fail(f"{category}[{index}].source_name is required when eligible")
            eligible.append((rate, name.strip()))
    if not eligible:
        return None, ZERO
    # Stable deterministic tie-breaking; either tied product gives the same rate.
    eligible.sort(key=lambda item: (-item[0], item[1].casefold()))
    return eligible[0][1], eligible[0][0]


def process(record):
    if not isinstance(record, dict):
        fail("each savings entry must be an object")
    savings_name = record.get("savings_name")
    if not isinstance(savings_name, str) or not savings_name.strip():
        fail("savings_name is required")
    savings_name = savings_name.strip()
    base = amount(record.get("base_apy_pct"), f"{savings_name}.base_apy_pct")
    checking_name, checking = choose(
        record.get("checking_candidates", []), "boost_apy_pct", f"{savings_name}.checking_candidates"
    )
    card_name, card = choose(
        record.get("card_candidates", []), "bonus_apy_pct", f"{savings_name}.card_candidates"
    )
    other = amount(record.get("other_bonus_apy_pct", 0), f"{savings_name}.other_bonus_apy_pct")
    total = base + checking + card + other
    if total <= ZERO:
        fail(f"{savings_name} total APY must be positive")

    checking_words = (
        f"{checking_name} supplies the highest eligible linked-checking boost, +{display(checking)}%"
        if checking_name else "no screened eligible linked-checking boost applies"
    )
    card_words = (
        f"{card_name} supplies the highest applicable card bonus, +{display(card)}%"
        if card_name else "no screened eligible card bonus applies"
    )
    summary = (
        f"For {savings_name}, the documented base APY is {display(base)}%. "
        f"{checking_words}, and {card_words}. The documented combined APY is {display(total)}%. "
        "Other checking boosts do not stack with the selected checking boost, and other card bonuses do not stack with the selected card bonus; "
        "the one selected checking boost and one selected card bonus can stack with the base APY."
    )
    return {
        "savings_name": savings_name,
        "selected_checking": None if checking_name is None else {
            "source_name": checking_name, "boost_apy_pct": float(checking)
        },
        "selected_card": None if card_name is None else {
            "source_name": card_name, "bonus_apy_pct": float(card)
        },
        "apy_components_pct": {
            "base": float(base), "checking": float(checking), "card": float(card),
            "other": float(other), "total_expected": float(total)
        },
        "customer_summary": summary
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            fail("input must be a JSON object")
        savings = payload.get("savings")
        if not isinstance(savings, list) or not savings:
            fail("savings must be a nonempty list")
        print(json.dumps({"accounts": [process(item) for item in savings]}, sort_keys=True))
    except (ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
