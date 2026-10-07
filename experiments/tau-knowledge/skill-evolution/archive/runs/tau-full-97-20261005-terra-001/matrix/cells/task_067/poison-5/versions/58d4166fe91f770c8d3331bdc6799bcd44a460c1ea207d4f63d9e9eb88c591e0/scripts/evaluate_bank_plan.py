#!/usr/bin/env python3
"""Rank documented savings APY plans without performing any banking action.

Read one JSON object from stdin and emit one JSON object to stdout.  Values for
amounts and APYs may be numbers or numeric strings.  Eligibility is true, false,
or null (unknown).
"""

import json
import sys
from decimal import Decimal, InvalidOperation


def number(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field} must be numeric")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def state(value, field):
    if value not in (True, False, None):
        raise ValueError(f"{field} must be true, false, or null")
    return value


def best_options(options, label_field, category):
    if options is None:
        options = []
    if not isinstance(options, list):
        raise ValueError(f"{category}_options must be a list")

    grouped = {True: [], None: [], False: []}
    for index, item in enumerate(options):
        if not isinstance(item, dict):
            raise ValueError(f"{category}_options[{index}] must be an object")
        label = item.get(label_field)
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"{category}_options[{index}].{label_field} is required")
        boost = number(item.get("boost_apy"), f"{category}_options[{index}].boost_apy")
        if boost < 0:
            raise ValueError(f"{category}_options[{index}].boost_apy cannot be negative")
        grouped[state(item.get("eligible"), f"{category}_options[{index}].eligible")].append(
            {"label": label, "boost": boost}
        )

    none = {"label": None, "boost": Decimal("0")}
    return {
        True: max(grouped[True], key=lambda x: x["boost"], default=none),
        None: max(grouped[None], key=lambda x: x["boost"], default=none),
    }


def render(candidate, checking, card, plan_state):
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
        "status": plan_state,
        "stacking_note": (
            "Projected APY uses base APY plus only the highest selected checking "
            "boost and highest selected card bonus. Checking boosts do not stack "
            "with checking boosts; card bonuses do not stack with card bonuses."
        ),
    }


def choose_verified_or_unknown(options):
    """Return the higher of verified and unknown options, retaining unknown if tied."""
    if options[None]["boost"] >= options[True]["boost"]:
        return options[None]
    return options[True]


def evaluate(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    target = number(payload.get("target_balance"), "target_balance")
    if target < 0:
        raise ValueError("target_balance cannot be negative")
    raw_candidates = payload.get("savings_candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise ValueError("savings_candidates must be a nonempty list")

    verified = []
    conditional = []
    rejected = []

    for index, raw in enumerate(raw_candidates):
        if not isinstance(raw, dict):
            raise ValueError(f"savings_candidates[{index}] must be an object")
        name = raw.get("savings_class")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"savings_candidates[{index}].savings_class is required")

        candidate = {
            "name": name,
            "base": number(raw.get("base_apy"), f"savings_candidates[{index}].base_apy"),
            "opening": number(raw.get("opening_deposit_minimum", 0), f"savings_candidates[{index}].opening_deposit_minimum"),
            "ongoing": number(raw.get("ongoing_balance_minimum", 0), f"savings_candidates[{index}].ongoing_balance_minimum"),
        }
        if min(candidate["base"], candidate["opening"], candidate["ongoing"]) < 0:
            raise ValueError(f"savings_candidates[{index}] contains a negative APY or amount")

        candidate_state = state(raw.get("eligible"), f"savings_candidates[{index}].eligible")
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

        checking = best_options(raw.get("checking_options", []), "checking_class", "checking")
        card = best_options(raw.get("card_options", []), "card_name", "card")

        if candidate_state is True:
            verified.append(render(candidate, checking[True], card[True], "verified"))
            if checking[None]["boost"] > checking[True]["boost"] or card[None]["boost"] > card[True]["boost"]:
                conditional.append(render(
                    candidate,
                    choose_verified_or_unknown(checking),
                    choose_verified_or_unknown(card),
                    "conditional",
                ))
        else:
            conditional.append(render(
                candidate,
                choose_verified_or_unknown(checking),
                choose_verified_or_unknown(card),
                "conditional",
            ))

    key = lambda plan: plan["projected_total_apy"]
    verified.sort(key=key, reverse=True)
    conditional.sort(key=key, reverse=True)
    return {
        "target_balance": float(target),
        "viable_plans": verified,
        "conditional_plans": conditional,
        "rejections": rejected,
        "recommendation_rule": (
            "Recommend only a viable plan after independently confirming official "
            "product names, customer authority, account eligibility, funding terms, "
            "and any required banking-action confirmations. Conditional plans require "
            "further verification and are not action authorization."
        ),
    }


def main():
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(evaluate(payload), sort_keys=True, separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
