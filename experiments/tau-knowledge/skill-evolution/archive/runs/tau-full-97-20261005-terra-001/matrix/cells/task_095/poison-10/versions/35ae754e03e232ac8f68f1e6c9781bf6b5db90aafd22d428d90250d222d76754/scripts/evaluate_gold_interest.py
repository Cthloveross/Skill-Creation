#!/usr/bin/env python3
"""Select Gold Account APY components and optionally estimate a stable-balance period.

Reads one JSON object from stdin. Emits {"ok": true, "result": ...} or
{"ok": false, "errors": [...]} on stdout. See SKILL.md for the schema.
"""
import json
import math
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CARD_BONUSES = {
    "Bronze Rewards Card": Decimal("0.15"),
    "Silver Rewards Card": Decimal("0.20"),
    "Gold Rewards Card": Decimal("0.025"),
    "Platinum Rewards Card": Decimal("0.15"),
    "Diamond Elite Card": Decimal("0.30"),
    "EcoCard": Decimal("0.60"),
    "Green Rewards Card": Decimal("0.35"),
    "Crypto-Cash Back Card": Decimal("0"),
}
GOLD_CHECKING_BOOSTS = {
    "Green Account": Decimal("0.75"),
    "Purple Account": Decimal("0.10"),
}
GOLD_REWARDS_RELATIONSHIP_BONUS = Decimal("0.025")


def decimal_value(value, field, errors, allow_zero=True):
    if isinstance(value, bool) or value is None:
        errors.append(f"{field} must be a number.")
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be a number.")
        return None
    if not number.is_finite() or number < 0 or (not allow_zero and number == 0):
        qualifier = "greater than zero" if not allow_zero else "zero or greater"
        errors.append(f"{field} must be {qualifier}.")
        return None
    return number


def pct(value):
    return float(value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def money(value):
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def active_same_profile_card(item):
    return (
        isinstance(item, dict)
        and str(item.get("status", "")).strip().upper() == "ACTIVE"
        and item.get("same_profile") is True
    )


def choose_highest(candidates, value_key):
    if not candidates:
        return None
    return sorted(candidates, key=lambda candidate: (-candidate[value_key], candidate["name"]))[0]


def run(data):
    if not isinstance(data, dict):
        return {"ok": False, "errors": ["Input must be a JSON object."]}

    errors = []
    account_type = str(data.get("savings_account_type", "Gold Account")).strip().lower()
    if account_type not in {"gold account", "gold savings", "gold savings account"}:
        return {"ok": False, "errors": ["This helper only supports a Gold Account."]}

    base = decimal_value(data.get("base_apy_percent"), "base_apy_percent", errors)
    checking = data.get("checking_accounts", [])
    cards = data.get("credit_cards", [])
    if not isinstance(checking, list):
        errors.append("checking_accounts must be a list.")
        checking = []
    if not isinstance(cards, list):
        errors.append("credit_cards must be a list.")
        cards = []
    if errors:
        return {"ok": False, "errors": errors}

    checking_candidates = []
    checking_excluded = []
    for item in checking:
        if not isinstance(item, dict):
            checking_excluded.append({"reason": "invalid item"})
            continue
        name = str(item.get("account_type", "")).strip()
        boost = GOLD_CHECKING_BOOSTS.get(name)
        if boost is None:
            checking_excluded.append({"account_type": name or None, "reason": "not a documented Gold Account qualifying checking type"})
        elif item.get("active") is not True:
            checking_excluded.append({"account_type": name, "reason": "not confirmed active"})
        elif item.get("same_profile") is not True:
            checking_excluded.append({"account_type": name, "reason": "not confirmed under the same profile"})
        else:
            checking_candidates.append({"name": name, "boost": boost})

    card_candidates = []
    card_excluded = []
    for item in cards:
        if not isinstance(item, dict):
            card_excluded.append({"reason": "invalid item"})
            continue
        name = str(item.get("card_type", "")).strip()
        bonus = CARD_BONUSES.get(name)
        if bonus is None:
            card_excluded.append({"card_type": name or None, "reason": "card bonus not documented by this helper"})
        elif str(item.get("status", "")).strip().upper() != "ACTIVE":
            card_excluded.append({"card_type": name, "reason": "not active"})
        elif item.get("same_profile") is not True:
            card_excluded.append({"card_type": name, "reason": "not confirmed under the same profile"})
        else:
            card_candidates.append({"name": name, "bonus": bonus})

    selected_checking = choose_highest(checking_candidates, "boost")
    selected_card = choose_highest(card_candidates, "bonus")
    checking_boost = selected_checking["boost"] if selected_checking else Decimal("0")
    card_bonus = selected_card["bonus"] if selected_card else Decimal("0")

    # This is intentionally separate from the Gold Rewards card-category bonus.
    # The latter competes with other card bonuses; this relationship benefit is additive.
    gold_rewards_relationship_active = any(
        candidate["name"] == "Gold Rewards Card" for candidate in card_candidates
    )
    relationship_bonus = (
        GOLD_REWARDS_RELATIONSHIP_BONUS if gold_rewards_relationship_active else Decimal("0")
    )
    expected = base + checking_boost + card_bonus + relationship_bonus

    relationship_bonuses = []
    if gold_rewards_relationship_active:
        relationship_bonuses.append({
            "relationship": "Gold Rewards Card holder relationship bonus",
            "bonus_percent": pct(relationship_bonus),
            "additive": True,
        })

    result = {
        "base_apy_percent": pct(base),
        "checking_candidates": [
            {"account_type": item["name"], "boost_percent": pct(item["boost"])}
            for item in checking_candidates
        ],
        "checking_excluded": checking_excluded,
        "selected_checking": None if selected_checking is None else {
            "account_type": selected_checking["name"],
            "boost_percent": pct(checking_boost),
        },
        "credit_card_candidates": [
            {"card_type": item["name"], "bonus_percent": pct(item["bonus"])}
            for item in card_candidates
        ],
        "credit_card_excluded": card_excluded,
        "selected_credit_card": None if selected_card is None else {
            "card_type": selected_card["name"],
            "bonus_percent": pct(card_bonus),
        },
        "relationship_bonuses": relationship_bonuses,
        "expected_apy_percent": pct(expected),
        "expected_apy_display_two_decimals": format(expected.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f"),
        "minimum_balance_requirement": 5000 if gold_rewards_relationship_active else 10000,
        "assumptions": [
            "Only the highest qualifying checking boost is selected.",
            "Only the highest active, same-profile credit-card bonus is selected.",
            "The Gold Rewards relationship bonus is separate from the nonstacking Gold Rewards card-category bonus and is additive when the card is active and same-profile.",
            "The selected checking boost, selected card bonus, and applicable relationship bonuses are additive to the supplied base APY.",
        ],
    }

    supplied_estimate = [key for key in ("balance", "days", "actual_interest") if key in data]
    if supplied_estimate and len(supplied_estimate) != 3:
        result["interest_comparison"] = {
            "status": "insufficient_inputs",
            "message": "Provide balance, days, and actual_interest together for a stable-balance estimate.",
        }
        return {"ok": True, "result": result}

    if not supplied_estimate:
        if "actual_apy_percent" in data:
            actual_apy = decimal_value(data["actual_apy_percent"], "actual_apy_percent", errors)
            if errors:
                return {"ok": False, "errors": errors}
            result["interest_comparison"] = {
                "status": "apy_comparison_only",
                "actual_apy_percent": pct(actual_apy),
                "expected_apy_percent": pct(expected),
                "apy_difference_percent": pct(expected - actual_apy),
                "message": "An APY difference still requires account, period, and daily-ledger verification before remediation.",
            }
        return {"ok": True, "result": result}

    balance = decimal_value(data["balance"], "balance", errors, allow_zero=False)
    days = data["days"]
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 366:
        errors.append("days must be an integer from 1 through 366.")
    actual_interest = decimal_value(data["actual_interest"], "actual_interest", errors)
    if errors:
        return {"ok": False, "errors": errors}

    expected_interest = balance * Decimal(str(
        math.pow(1.0 + float(expected / Decimal("100")), days / 365.0) - 1.0
    ))
    difference = expected_interest - actual_interest
    implied_actual_apy = (
        math.pow(1.0 + float(actual_interest / balance), 365.0 / days) - 1.0
    ) * 100.0
    result["interest_comparison"] = {
        "status": "indicative_stable_balance_estimate",
        "balance": money(balance),
        "days": days,
        "expected_interest": money(expected_interest),
        "actual_interest": money(actual_interest),
        "estimated_difference": money(difference),
        "implied_actual_apy_percent": round(implied_actual_apy, 3),
        "message": "This comparison assumes the supplied balance was constant every day and is not sufficient alone to authorize a credit or discrepancy report.",
    }
    return {"ok": True, "result": result}


def main():
    try:
        print(json.dumps(run(json.load(sys.stdin)), separators=(",", ":"), allow_nan=False))
    except json.JSONDecodeError:
        print(json.dumps({"ok": False, "errors": ["stdin must contain valid JSON."]}, separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [f"Unexpected evaluation error: {exc}"]}, separators=(",", ":")))


if __name__ == "__main__":
    main()
