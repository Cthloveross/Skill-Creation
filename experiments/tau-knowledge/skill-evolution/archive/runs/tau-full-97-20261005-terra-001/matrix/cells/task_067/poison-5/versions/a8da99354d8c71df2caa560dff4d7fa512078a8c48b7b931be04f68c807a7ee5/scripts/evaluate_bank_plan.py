#!/usr/bin/env python3
"""Rank documented savings APY combinations without executing banking actions.

Reads one JSON object from stdin and emits one JSON object on stdout. See SKILL.md
for the input schema. Amounts and APYs may be JSON numbers or numeric strings.
"""

import json
import sys
from decimal import Decimal, InvalidOperation


def decimal(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be numeric")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def eligibility(value, field):
    if value not in (True, False, None):
        raise ValueError(f"{field} must be true, false, or null")
    return value


def max_option(options, label_key, category):
    """Return a best option per eligibility state, including a no-boost baseline."""
    if options is None:
        options = []
    if not isinstance(options, list):
        raise ValueError(f"{category}_options must be a list")
    states = {True: [], None: [], False: []}
    for index, option in enumerate(options):
        if not isinstance(option, dict):
            raise ValueError(f"{category}_options[{index}] must be an object")
        label = option.get(label_key)
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"{category}_options[{index}].{label_key} is required")
        boost = decimal(option.get("boost_apy"), f"{category}_options[{index}].boost_apy")
        if boost < 0:
            raise ValueError(f"{category}_options[{index}].boost_apy cannot be negative")
        state = eligibility(option.get("eligible"), f"{category}_options[{index}].eligible")
        states[state].append({"label": label, "boost": boost})

    # A customer can always receive no boost from this category. It makes the
    # non-stacking policy explicit rather than requiring a fake product record.
    baseline = {"label": None, "boost": Decimal("0")}
    result = {}
    for state in (True, None):
        candidates = states[state]
        result[state] = max(candidates, key=lambda item: item["boost"]) if candidates else baseline
    return result


def plan_for(candidate, checking, card, status):
    total = candidate["base"] + checking["boost"] + card["boost"]
    return {
        "savings_class": candidate["name"],
        "checking_class": checking["label"],
        "credit_card": card["label"],
        "base_apy": float(candidate["base"]),
        "checking_boost_apy": float(checking["boost"]),
        "credit_card_boost_apy": float(card["boost"]),
        "projected_total_apy": float(total),
        "opening_deposit_minimum": float(candidate["opening_min"]),
        "ongoing_balance_minimum": float(candidate["ongoing_min"]),
        "status": status,
        "stacking_note": "Only the highest applicable checking boost and highest applicable card boost are used; one selected boost from each category is combined with the base APY."
    }


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    target = decimal(payload.get("target_balance"), "target_balance")
    if target < 0:
        raise ValueError("target_balance cannot be negative")
    candidates = payload.get("savings_candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("savings_candidates must be a nonempty list")

    viable, conditional, rejections = [], [], []
    for index, raw in enumerate(candidates):
        if not isinstance(raw, dict):
            raise ValueError(f"savings_candidates[{index}] must be an object")
        name = raw.get("savings_class")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"savings_candidates[{index}].savings_class is required")
        base = decimal(raw.get("base_apy"), f"savings_candidates[{index}].base_apy")
        opening = decimal(raw.get("opening_deposit_minimum", 0), f"savings_candidates[{index}].opening_deposit_minimum")
        ongoing = decimal(raw.get("ongoing_balance_minimum", 0), f"savings_candidates[{index}].ongoing_balance_minimum")
        if min(base, opening, ongoing) < 0:
            raise ValueError(f"savings_candidates[{index}] has a negative amount or APY")
        candidate_state = eligibility(raw.get("eligible"), f"savings_candidates[{index}].eligible")
        candidate = {"name": name, "base": base, "opening_min": opening, "ongoing_min": ongoing}

        reasons = []
        if target < opening:
            reasons.append("target balance is below the documented opening-deposit minimum")
        if target < ongoing:
            reasons.append("target balance is below the documented ongoing-balance minimum")
        if candidate_state is False:
            reasons.append("savings product eligibility is not met")
        if reasons:
            rejections.append({"savings_class": name, "reasons": reasons})
            continue

        checking = max_option(raw.get("checking_options", []), "checking_class", "checking")
        card = max_option(raw.get("card_options", []), "card_name", "card")
        if candidate_state is True:
            viable.append(plan_for(candidate, checking[True], card[True], "verified"))
            # Unknown boosts could make a higher conditional plan, but cannot
            # make the verified recommendation.
            unknown_check = checking[None]
            unknown_card = card[None]
            if unknown_check["boost"] > checking[True]["boost"] or unknown_card["boost"] > card[True]["boost"]:
                conditional.append(plan_for(candidate, unknown_check if unknown_check["boost"] > checking[True]["boost"] else checking[True], unknown_card if unknown_card["boost"] > card[True]["boost"] else card[True], "conditional"))
        else:
            # The product itself is unverified; choose the best possible
            # documented options but retain a conditional status.
            best_check = checking[None] if checking[None]["boost"] >= checking[True]["boost"] else checking[True]
            best_card = card[None] if card[None]["boost"] >= card[True]["boost"] else card[True]
            conditional.append(plan_for(candidate, best_check, best_card, "conditional"))

    key = lambda p: p["projected_total_apy"]
    viable.sort(key=key, reverse=True)
    conditional.sort(key=key, reverse=True)
    return {
        "target_balance": float(target),
        "viable_plans": viable,
        "conditional_plans": conditional,
        "rejections": rejections,
        "recommendation_rule": "Recommend only the first viable plan after independently verifying ownership, product eligibility, exact official account classes, fees, funding, and required customer confirmations. Conditional plans require further verification and are not action authorization."
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), separators=(",", ":"), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
