#!/usr/bin/env python3
"""Evaluate documented savings APY plans without performing banking actions.

Reads one JSON object from stdin and writes one JSON object to stdout. Amounts and
APYs may be JSON numbers or numeric strings. Eligibility values are true, false,
or null (unknown/conditional).
"""

import json
import sys
from decimal import Decimal, InvalidOperation


def decimal(value, field):
    try:
        value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field} must be numeric")
    if not value.is_finite():
        raise ValueError(f"{field} must be finite")
    return value


def eligibility(value, field):
    if value not in (True, False, None):
        raise ValueError(f"{field} must be true, false, or null")
    return value


def best_by_state(options, label_key, group_name):
    if options is None:
        options = []
    if not isinstance(options, list):
        raise ValueError(f"{group_name}_options must be a list")
    grouped = {True: [], None: []}
    for index, option in enumerate(options):
        if not isinstance(option, dict):
            raise ValueError(f"{group_name}_options[{index}] must be an object")
        label = option.get(label_key)
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"{group_name}_options[{index}].{label_key} is required")
        boost = decimal(option.get("boost_apy"), f"{group_name}_options[{index}].boost_apy")
        if boost < 0:
            raise ValueError(f"{group_name}_options[{index}].boost_apy cannot be negative")
        state = eligibility(option.get("eligible"), f"{group_name}_options[{index}].eligible")
        if state is not False:
            grouped[state].append({"label": label, "boost": boost})
    empty = {"label": None, "boost": Decimal("0")}
    return {
        True: max(grouped[True], key=lambda item: item["boost"], default=empty),
        None: max(grouped[None], key=lambda item: item["boost"], default=empty),
    }


def best_known_or_conditional(options):
    """Choose the larger boost, preferring conditional on a tie to preserve its state."""
    if options[None]["boost"] >= options[True]["boost"]:
        return options[None]
    return options[True]


def render(candidate, checking, card, status):
    total = candidate["base"] + checking["boost"] + card["boost"]
    return {
        "savings_class": candidate["name"],
        "checking_class": checking["label"],
        "credit_card": card["label"],
        "base_apy": float(candidate["base"]),
        "checking_boost_apy": float(checking["boost"]),
        "credit_card_boost_apy": float(card["boost"]),
        "projected_total_apy": float(total),
        "opening_deposit_minimum": float(candidate["opening"]),
        "ongoing_balance_minimum": float(candidate["ongoing"]),
        "status": status,
        "stacking_note": "Uses base APY plus only the highest applicable checking boost and highest applicable card bonus.",
    }


def evaluate(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    target = decimal(payload.get("target_balance"), "target_balance")
    if target < 0:
        raise ValueError("target_balance cannot be negative")
    candidates = payload.get("savings_candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("savings_candidates must be a nonempty list")

    viable, conditional, rejected = [], [], []
    for index, raw in enumerate(candidates):
        if not isinstance(raw, dict):
            raise ValueError(f"savings_candidates[{index}] must be an object")
        name = raw.get("savings_class")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"savings_candidates[{index}].savings_class is required")
        candidate = {
            "name": name,
            "base": decimal(raw.get("base_apy"), f"savings_candidates[{index}].base_apy"),
            "opening": decimal(raw.get("opening_deposit_minimum", 0), f"savings_candidates[{index}].opening_deposit_minimum"),
            "ongoing": decimal(raw.get("ongoing_balance_minimum", 0), f"savings_candidates[{index}].ongoing_balance_minimum"),
        }
        if min(candidate["base"], candidate["opening"], candidate["ongoing"]) < 0:
            raise ValueError(f"savings_candidates[{index}] contains a negative value")
        candidate_state = eligibility(raw.get("eligible"), f"savings_candidates[{index}].eligible")
        reasons = []
        if target < candidate["opening"]:
            reasons.append("target balance is below opening-deposit minimum")
        if target < candidate["ongoing"]:
            reasons.append("target balance is below ongoing-balance minimum")
        if candidate_state is False:
            reasons.append("savings-product eligibility is not met")
        if reasons:
            rejected.append({"savings_class": name, "reasons": reasons})
            continue

        checking = best_by_state(raw.get("checking_options", []), "checking_class", "checking")
        cards = best_by_state(raw.get("card_options", []), "card_name", "card")
        if candidate_state is True:
            viable.append(render(candidate, checking[True], cards[True], "viable"))
            if checking[None]["boost"] > checking[True]["boost"] or cards[None]["boost"] > cards[True]["boost"]:
                conditional.append(render(candidate, best_known_or_conditional(checking), best_known_or_conditional(cards), "conditional"))
        else:
            conditional.append(render(candidate, best_known_or_conditional(checking), best_known_or_conditional(cards), "conditional"))

    key = lambda plan: plan["projected_total_apy"]
    viable.sort(key=key, reverse=True)
    conditional.sort(key=key, reverse=True)
    return {
        "target_balance": float(target),
        "viable_plans": viable,
        "conditional_plans": conditional,
        "rejections": rejected,
        "action_warning": "This output is not account-opening, closure, funding, transfer, or credit-card authorization. Independently verify all required banking controls before acting.",
    }


def main():
    try:
        print(json.dumps(evaluate(json.load(sys.stdin)), sort_keys=True, separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
