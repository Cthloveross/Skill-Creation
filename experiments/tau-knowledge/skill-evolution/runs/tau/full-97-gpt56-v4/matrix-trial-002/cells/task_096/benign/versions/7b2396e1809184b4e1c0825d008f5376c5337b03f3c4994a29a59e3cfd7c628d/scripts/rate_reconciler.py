#!/usr/bin/env python3
"""Calculate documented savings APY components from JSON on stdin.

Input schema:
{
  "savings_accounts": [{
    "type": "Bronze" | "Gold Plus",
    "checking_accounts": [string, ...],
    "credit_cards": [string, ...],
    "approximate_balance": number (optional),
    "days_in_period": integer (optional),
    "daily_balances": [number, ...] (optional)
  }]
}

Output schema: {"accounts": [result, ...], "errors": [string, ...]}.
Rates are percentages (e.g. 3.0 means 3.0% APY). The script is informational;
it makes no account changes.
"""
import json
import math
import sys

BASE_APY = {"Bronze": 2.0, "Gold Plus": 6.0}
CHECKING_BOOSTS = {
    "Bronze": {
        "Bluest Account": 0.7,
        "Green Fee-Free Account": 0.4,
    },
    "Gold Plus": {
        "Gold Years Account": 0.5,
        "Green Fee-Free Account": 0.35,
    },
}
CARD_BONUSES = {
    "Bronze": {
        "Bronze Rewards Card": 0.1,
        "Silver Rewards Card": 0.0,
        "Gold Rewards Card": 0.25,
        "EcoCard": 0.0,
        "Green Rewards Card": 0.2,
        "Crypto-Cash Back Card": 0.3,
    },
    "Gold Plus": {
        "Bronze Rewards Card": 0.15,
        "Silver Rewards Card": 0.1,
        "Gold Rewards Card": 0.35,
        "Platinum Rewards Card": 0.2,
        "Diamond Elite Card": 0.25,
        "EcoCard": 0.1,
        "Green Rewards Card": 0.05,
        "Crypto-Cash Back Card": 0.3,
    },
}


def clean_name(value):
    return value.strip() if isinstance(value, str) else ""


def qualifying(held, schedule):
    """Return documented held products and their percentage bonuses."""
    return [{"product": name, "bonus_apy_percent": schedule[name]}
            for name in (clean_name(x) for x in held) if name in schedule]


def choose_highest(items):
    # Stable secondary sort makes ties deterministic without changing the rate.
    if not items:
        return None
    return sorted(items, key=lambda x: (-x["bonus_apy_percent"], x["product"]))[0]


def interest_estimate(apy_percent, daily_balances):
    daily_rate = math.pow(1.0 + apy_percent / 100.0, 1.0 / 365.0) - 1.0
    return sum(balance * daily_rate for balance in daily_balances)


def account_result(account, index):
    if not isinstance(account, dict):
        return None, "savings_accounts[%d] must be an object" % index
    kind = clean_name(account.get("type"))
    if kind not in BASE_APY:
        return {
            "type": kind or None,
            "supported": False,
            "message": "Unsupported savings type. No rate was calculated."
        }, None

    held_checking = account.get("checking_accounts", [])
    held_cards = account.get("credit_cards", [])
    if not isinstance(held_checking, list) or not isinstance(held_cards, list):
        return None, "checking_accounts and credit_cards must be arrays for account %d" % index

    checking_candidates = qualifying(held_checking, CHECKING_BOOSTS[kind])
    card_candidates = qualifying(held_cards, CARD_BONUSES[kind])
    selected_checking = choose_highest(checking_candidates)
    selected_card = choose_highest(card_candidates)
    checking_bonus = selected_checking["bonus_apy_percent"] if selected_checking else 0.0
    card_bonus = selected_card["bonus_apy_percent"] if selected_card else 0.0
    total = BASE_APY[kind] + checking_bonus + card_bonus

    result = {
        "type": kind,
        "supported": True,
        "base_apy_percent": BASE_APY[kind],
        "qualifying_checking_boosts": checking_candidates,
        "selected_checking_boost": selected_checking,
        "qualifying_card_bonuses": card_candidates,
        "selected_card_bonus": selected_card,
        "total_apy_percent": total,
        "policy": {
            "checking_boosts_stack_with_each_other": False,
            "card_bonuses_stack_with_each_other": False,
            "selected_checking_and_card_components_stack": True
        },
        "exact_credit_status": "Statement dates and daily eligible balances are required for an exact reconciliation."
    }

    balances = account.get("daily_balances")
    if balances is not None:
        if (not isinstance(balances, list) or not balances or
                any(isinstance(x, bool) or not isinstance(x, (int, float)) or x < 0 for x in balances)):
            result["estimate_status"] = "daily_balances was supplied but is not a nonempty array of nonnegative numbers."
        else:
            estimate = interest_estimate(total, balances)
            result["interest_estimate"] = {
                "days": len(balances),
                "method": "sum of daily eligible balances times the daily rate implied by total APY",
                "estimated_interest": round(estimate, 2),
                "currency": "USD",
                "not_an_exact_posting": True
            }
    elif "approximate_balance" in account or "days_in_period" in account:
        balance = account.get("approximate_balance")
        days = account.get("days_in_period")
        if (isinstance(balance, bool) or not isinstance(balance, (int, float)) or balance < 0 or
                isinstance(days, bool) or not isinstance(days, int) or days <= 0):
            result["estimate_status"] = "An estimate requires nonnegative approximate_balance and positive integer days_in_period."
        else:
            estimate = interest_estimate(total, [balance] * days)
            result["interest_estimate"] = {
                "days": days,
                "method": "constant approximate balance compounded daily at total APY",
                "estimated_interest": round(estimate, 2),
                "currency": "USD",
                "not_an_exact_posting": True
            }
    return result, None


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        print(json.dumps({"accounts": [], "errors": ["Invalid JSON input: %s" % exc]}))
        return
    accounts = payload.get("savings_accounts") if isinstance(payload, dict) else None
    if not isinstance(accounts, list):
        print(json.dumps({"accounts": [], "errors": ["savings_accounts must be an array"]}))
        return
    output = {"accounts": [], "errors": []}
    for index, account in enumerate(accounts):
        result, error = account_result(account, index)
        if error:
            output["errors"].append(error)
        elif result is not None:
            output["accounts"].append(result)
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
