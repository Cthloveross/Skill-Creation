#!/usr/bin/env python3
"""Calculate documented savings interest components from case evidence.

Reads one JSON object from stdin and writes one JSON object to stdout. No external
packages, files, bank tools, or network access are used.
"""
import json
import math
import sys
from decimal import Decimal, ROUND_HALF_UP

# Product policy encoded from packaged rate_rules.md. Values are percentage points.
POLICIES = {
    "Silver": {
        "tiers": [(10000.0, 4.0), (0.0, 2.5)],
        "cards": {"Bronze Rewards Card": 0.0, "Silver Rewards Card": 0.1,
                  "Gold Rewards Card": 0.5, "Platinum Rewards Card": 0.2,
                  "Diamond Elite Card": 0.25, "EcoCard": 2.2,
                  "Green Rewards Card": 0.0, "Crypto-Cash Back Card": 0.5},
        "checking": {"Bluest": 0.45},
        "relationship_default": 0.025,
    },
    "Silver Plus": {
        "tiers": [(15000.0, 4.5), (0.0, 3.0)],
        "cards": {"Bronze Rewards Card": 0.15, "Silver Rewards Card": 0.15,
                  "Gold Rewards Card": 0.2, "Platinum Rewards Card": 0.15,
                  "Diamond Elite Card": 0.4, "EcoCard": 0.45,
                  "Green Rewards Card": 0.1, "Crypto-Cash Back Card": 0.0},
        "checking": {"Blue": 0.35},
        "relationship_default": 0.025,
    },
    "Platinum": {
        "tiers": [(0.0, 6.5)],
        "cards": {"Bronze Rewards Card": 0.0, "Silver Rewards Card": 0.0,
                  "Gold Rewards Card": 0.15, "Platinum Rewards Card": 0.25,
                  "Diamond Elite Card": 0.35, "EcoCard": 0.0,
                  "Green Rewards Card": 0.0, "Crypto-Cash Back Card": 0.0},
        "checking": {"Blue": 0.8, "Light Green": 0.65},
        "relationship_default": None,
    },
    "Diamond Elite": {
        "tiers": [(0.0, 7.5)],
        "cards": {"Bronze Rewards Card": 0.0, "Silver Rewards Card": 0.0,
                  "Gold Rewards Card": 0.0, "Platinum Rewards Card": 0.1,
                  "Diamond Elite Card": 0.5, "EcoCard": 0.0,
                  "Green Rewards Card": 0.0, "Crypto-Cash Back Card": 0.15},
        "checking": {"Light Green": 0.2, "Evergreen": 0.15},
        "relationship_default": None,
    },
}


def cents(value):
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def active(item):
    return str(item.get("status", "")).upper() == "ACTIVE"


def tier_rate(policy, balance):
    for threshold, rate in policy["tiers"]:
        if balance >= threshold:
            return rate
    raise ValueError("No tier matches balance")


def selected_card(policy, cards):
    candidates, unknown = [], []
    for card in cards:
        if not active(card):
            continue
        name = card.get("card_type")
        if name in policy["cards"]:
            candidates.append((policy["cards"][name], name))
        else:
            unknown.append(name)
    return max(candidates, default=(0.0, None)), unknown


def selected_checking(policy, checking):
    candidates = []
    for account in checking or []:
        if active(account) and account.get("linked") is True:
            name = account.get("account_type")
            if name in policy["checking"]:
                candidates.append((policy["checking"][name], name))
    return max(candidates, default=(0.0, None))


def relationship_component(account, policy, warnings):
    if not account.get("relationship_bonus_verified", False):
        return 0.0
    supplied = account.get("relationship_bonus_percent")
    if supplied is not None:
        try:
            amount = float(supplied)
        except (TypeError, ValueError):
            raise ValueError("relationship_bonus_percent must be numeric")
        if amount < 0:
            raise ValueError("relationship_bonus_percent cannot be negative")
        return amount
    if policy["relationship_default"] is not None:
        return policy["relationship_default"]
    warnings.append("Relationship eligibility was marked verified but no documented amount was supplied for this product; no relationship amount was added.")
    return 0.0


def calculate_account(account, cards):
    account_type = account.get("account_type")
    result = {"account_id": account.get("account_id"), "account_type": account_type}
    if account_type not in POLICIES:
        result.update({"status": "unsupported_account_type", "warnings": ["This calculator supports only Silver, Silver Plus, Platinum, and Diamond Elite."]})
        return result
    if not active(account):
        result.update({"status": "insufficient_daily_balance_data", "warnings": ["Savings account is not marked ACTIVE; do not use this result for a correction."]})
        return result

    policy = POLICIES[account_type]
    warnings = []
    (card_bonus, card_name), unknown_cards = selected_card(policy, cards)
    checking_bonus, checking_name = selected_checking(policy, account.get("linked_checking", []))
    relationship_bonus = relationship_component(account, policy, warnings)
    direct_deposit_bonus = 0.25 if account_type == "Silver Plus" and account.get("direct_deposit_active") is True else 0.0
    if account_type == "Silver Plus" and account.get("direct_deposit_active") is None:
        warnings.append("Silver Plus direct-deposit status is unknown; no direct-deposit bonus was added.")

    result.update({
        "selected_card": card_name,
        "selected_card_bonus_percent": card_bonus,
        "selected_checking": checking_name,
        "selected_checking_bonus_percent": checking_bonus,
        "direct_deposit_bonus_percent": direct_deposit_bonus,
        "relationship_bonus_percent": relationship_bonus,
        "unrecognized_active_cards": unknown_cards,
        "warnings": warnings,
    })

    balances = account.get("daily_principal_balances")
    if not isinstance(balances, list) or not balances:
        result["status"] = "insufficient_daily_balance_data"
        result["required_evidence"] = "Provide ordered daily ending principal balances for the statement period and the posted interest-credit amount/date."
        return result

    try:
        daily_balances = [float(x) for x in balances]
    except (TypeError, ValueError):
        raise ValueError("daily_principal_balances must contain numeric values")
    if any(x < 0 for x in daily_balances):
        raise ValueError("daily_principal_balances cannot contain negative values")

    # Interest is accrued daily. Accrued interest is carried forward so a constant
    # principal balance produces daily compounding before monthly crediting.
    accrued = 0.0
    daily_rates = []
    for balance in daily_balances:
        base = tier_rate(policy, balance)
        annual_apy = base + card_bonus + checking_bonus + direct_deposit_bonus + relationship_bonus
        daily_rate = math.pow(1.0 + annual_apy / 100.0, 1.0 / 365.0) - 1.0
        accrued = (balance + accrued) * daily_rate + accrued
        daily_rates.append({"base_apy_percent": base, "total_apy_percent": annual_apy})

    expected = cents(accrued)
    unique_apys = sorted(set(x["total_apy_percent"] for x in daily_rates))
    result.update({
        "statement_days": len(daily_balances),
        "daily_rate_summary": daily_rates,
        "total_apy_percent_values": unique_apys,
        "expected_interest": float(expected),
    })
    if "actual_interest_credit" not in account or account["actual_interest_credit"] is None:
        result["status"] = "calculation_ready"
    else:
        try:
            actual = cents(account["actual_interest_credit"])
        except Exception as exc:
            raise ValueError("actual_interest_credit must be numeric") from exc
        result.update({
            "actual_interest_credit": float(actual),
            "amount_difference_expected_minus_actual": float(cents(expected - actual)),
            "status": "reconciled",
        })
    return result


def main(payload):
    accounts = payload.get("savings_accounts")
    cards = payload.get("credit_cards", [])
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("savings_accounts must be a nonempty list")
    if not isinstance(cards, list):
        raise ValueError("credit_cards must be a list")
    return {"results": [calculate_account(account, cards) for account in accounts]}


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), separators=(",", ":"), allow_nan=False))
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)
