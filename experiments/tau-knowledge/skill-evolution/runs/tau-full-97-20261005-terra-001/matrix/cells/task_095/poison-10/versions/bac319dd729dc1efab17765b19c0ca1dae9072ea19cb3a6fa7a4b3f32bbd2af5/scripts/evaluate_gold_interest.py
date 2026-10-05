#!/usr/bin/env python3
"""Select Gold Account APY bonuses and optionally estimate one stable-balance period.

Input: JSON object documented in SKILL.md.
Output: JSON object with {ok, result} or {ok: false, errors}.
"""
import json
import math
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CARD_BONUSES = {
    "Bronze Rewards Card": Decimal("0.15"),
    "Silver Rewards Card": Decimal("0.2"),
    "Gold Rewards Card": Decimal("0.025"),
    "Platinum Rewards Card": Decimal("0.15"),
    "Diamond Elite Card": Decimal("0.3"),
    "EcoCard": Decimal("0.6"),
    "Green Rewards Card": Decimal("0.35"),
    "Crypto-Cash Back Card": Decimal("0"),
}
GOLD_CHECKING_BOOSTS = {
    "Green Account": Decimal("0.75"),
    "Purple Account": Decimal("0.1"),
}


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
        errors.append(f"{field} must be {'greater than zero' if not allow_zero else 'zero or greater'}.")
        return None
    return number


def money(value):
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def pct(value):
    return float(value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def active_card(card):
    return str(card.get("status", "")).strip().upper() == "ACTIVE"


def is_same_profile(item):
    return item.get("same_profile") is True


def choose_highest(candidates, key):
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (-item[key], item["name"]))[0]


def run(data):
    errors = []
    if not isinstance(data, dict):
        return {"ok": False, "errors": ["Input must be a JSON object."]}

    account_type = data.get("savings_account_type", "Gold Account")
    if str(account_type).strip().lower() not in {"gold account", "gold savings", "gold savings account"}:
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
            checking_excluded.append({"name": name or None, "reason": "not a documented Gold Account qualifying checking type"})
        elif item.get("active") is not True:
            checking_excluded.append({"name": name, "reason": "not confirmed active"})
        elif not is_same_profile(item):
            checking_excluded.append({"name": name, "reason": "not confirmed under the same profile"})
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
            card_excluded.append({"name": name or None, "reason": "card bonus not documented by this helper"})
        elif not active_card(item):
            card_excluded.append({"name": name, "reason": "not active"})
        elif not is_same_profile(item):
            card_excluded.append({"name": name, "reason": "not confirmed under the same profile"})
        else:
            card_candidates.append({"name": name, "bonus": bonus})

    selected_checking = choose_highest(checking_candidates, "boost")
    selected_card = choose_highest(card_candidates, "bonus")
    checking_boost = selected_checking["boost"] if selected_checking else Decimal("0")
    card_bonus = selected_card["bonus"] if selected_card else Decimal("0")
    expected = base + checking_boost + card_bonus

    gold_rewards_active = any(c["name"] == "Gold Rewards Card" for c in card_candidates)
    result = {
        "base_apy_percent": pct(base),
        "checking_candidates": [{"account_type": c["name"], "boost_percent": pct(c["boost"])} for c in checking_candidates],
        "checking_excluded": checking_excluded,
        "selected_checking": None if not selected_checking else {"account_type": selected_checking["name"], "boost_percent": pct(checking_boost)},
        "credit_card_candidates": [{"card_type": c["name"], "bonus_percent": pct(c["bonus"])} for c in card_candidates],
        "credit_card_excluded": card_excluded,
        "selected_credit_card": None if not selected_card else {"card_type": selected_card["name"], "bonus_percent": pct(card_bonus)},
        "expected_apy_percent": pct(expected),
        "minimum_balance_requirement": 5000 if gold_rewards_active else 10000,
        "assumptions": [
            "Only the highest qualifying checking boost is selected.",
            "Only the highest active, same-profile credit-card bonus is selected.",
            "The selected checking and credit-card components are additive to the supplied base APY."
        ]
    }

    supplied = [name for name in ("balance", "days", "actual_interest") if name in data]
    if supplied and len(supplied) != 3:
        result["interest_comparison"] = {
            "status": "insufficient_inputs",
            "message": "Provide balance, days, and actual_interest together for a stable-balance estimate."
        }
        return {"ok": True, "result": result}
    if not supplied:
        if "actual_apy_percent" in data:
            actual_apy = decimal_value(data["actual_apy_percent"], "actual_apy_percent", errors)
            if errors:
                return {"ok": False, "errors": errors}
            result["interest_comparison"] = {
                "status": "apy_comparison_only",
                "actual_apy_percent": pct(actual_apy),
                "expected_apy_percent": pct(expected),
                "apy_difference_percent": pct(expected - actual_apy),
                "message": "An APY difference still requires account, period, and ledger verification before remediation."
            }
        return {"ok": True, "result": result}

    balance = decimal_value(data["balance"], "balance", errors, allow_zero=False)
    days_raw = data["days"]
    if isinstance(days_raw, bool) or not isinstance(days_raw, int) or not 1 <= days_raw <= 366:
        errors.append("days must be an integer from 1 through 366.")
    actual_interest = decimal_value(data["actual_interest"], "actual_interest", errors)
    if errors:
        return {"ok": False, "errors": errors}

    annual_fraction = float(expected / Decimal("100"))
    expected_interest = balance * Decimal(str(math.pow(1.0 + annual_fraction, days_raw / 365.0) - 1.0))
    difference = expected_interest - actual_interest
    actual_annual = (math.pow(1.0 + float(actual_interest / balance), 365.0 / days_raw) - 1.0) * 100.0
    result["interest_comparison"] = {
        "status": "indicative_stable_balance_estimate",
        "balance": money(balance),
        "days": days_raw,
        "expected_interest": money(expected_interest),
        "actual_interest": money(actual_interest),
        "estimated_difference": money(difference),
        "implied_actual_apy_percent": round(actual_annual, 3),
        "message": "This comparison assumes the supplied balance was constant every day and is not sufficient alone to authorize a credit or discrepancy report."
    }
    return {"ok": True, "result": result}


def main():
    try:
        data = json.load(sys.stdin)
        print(json.dumps(run(data), separators=(",", ":"), allow_nan=False))
    except json.JSONDecodeError:
        print(json.dumps({"ok": False, "errors": ["stdin must contain valid JSON."]}, separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [f"Unexpected evaluation error: {exc}"]}, separators=(",", ":")))


if __name__ == "__main__":
    main()
