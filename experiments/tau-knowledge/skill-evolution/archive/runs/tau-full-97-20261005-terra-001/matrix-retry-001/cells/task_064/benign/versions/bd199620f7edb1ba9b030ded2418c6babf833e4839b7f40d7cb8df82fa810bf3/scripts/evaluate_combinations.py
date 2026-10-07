#!/usr/bin/env python3
"""Rank documented savings/card combinations.

Read one JSON object from stdin and write one JSON object to stdout. The optional
expected_monthly_withdrawals field is evaluated against documented account limits.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

CENT = Decimal("0.01")


def numeric(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field} must be numeric")
    if result < 0:
        raise ValueError(f"{field} must not be negative")
    return result


def whole_number(value, field):
    number = numeric(value, field)
    if number != number.to_integral_value():
        raise ValueError(f"{field} must be a whole number")
    return int(number)


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def text(value):
    return format(value, "f")


def card_reasons(card, data):
    reasons = []
    score = data.get("credit_score")
    minimum = card.get("minimum_credit_score")
    if minimum is not None:
        if score is None:
            reasons.append("credit score is not supplied")
        elif numeric(score, "credit_score") < Decimal(str(minimum)):
            reasons.append(f"credit score is below the required {minimum}")
    if card.get("requires_premium_subscription") and not data.get("has_premium_subscription", False):
        reasons.append("requires an active premium subscription")
    explicit = data.get("card_eligibility", {}).get(card["name"])
    if card.get("requires_invitation") and explicit is not True:
        reasons.append("requires an invitation confirmed through card_eligibility")
    if card.get("requires_explicit_eligibility_confirmation") and explicit is not True:
        reasons.append("requires explicit eligibility confirmation through card_eligibility")
    return reasons


def highest_checking_boost(boosts, account_name):
    values = []
    for item in boosts:
        if isinstance(item, dict) and item.get("savings_account") == account_name:
            values.append(numeric(item.get("apy_percent"), "checking_boosts[].apy_percent"))
    return max(values) if values else Decimal("0")


def additive_bonuses(bonuses, account_name):
    total, labels = Decimal("0"), []
    for item in bonuses:
        if isinstance(item, dict) and item.get("savings_account") == account_name:
            total += numeric(item.get("apy_percent"), "other_additive_bonuses[].apy_percent")
            labels.append(item.get("label", "verified additive bonus"))
    return total, labels


def withdrawal_detail(account):
    limit = account.get("monthly_withdrawal_limit")
    if limit == -1:
        return {"documented": True, "limit": "unlimited"}
    if limit is None:
        return {"documented": False, "limit": None}
    return {"documented": True, "limit": limit}


def main(data):
    balance = numeric(data.get("balance"), "balance")
    if balance == 0:
        raise ValueError("balance must be greater than zero for an earnings comparison")
    expected_withdrawals = None
    if "expected_monthly_withdrawals" in data:
        expected_withdrawals = whole_number(data["expected_monthly_withdrawals"], "expected_monthly_withdrawals")
    if not isinstance(data.get("card_eligibility", {}), dict):
        raise ValueError("card_eligibility must be an object")
    boosts = data.get("checking_boosts", [])
    bonuses = data.get("other_additive_bonuses", [])
    if not isinstance(boosts, list) or not isinstance(bonuses, list):
        raise ValueError("checking_boosts and other_additive_bonuses must be arrays")

    path = Path(__file__).resolve().parents[1] / "references" / "financial-combination-catalog.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    subscription = data.get("subscription", {})
    if not isinstance(subscription, dict):
        raise ValueError("subscription must be an object")
    subscription_cost = numeric(subscription.get("monthly_cost", catalog["premium_subscription"]["monthly_cost"]), "subscription.monthly_cost")
    charge_subscription = bool(subscription.get("incremental_for_comparison", False))

    warnings = [
        "Results assume the supplied balance is held for the full year and all product eligibility remains active.",
        "Operational eligibility to open a personal savings account is not verified by this calculator.",
        "Cash back, taxes, maintenance fees caused by falling below minimums, and undocumented boosts are excluded."
    ]
    if not charge_subscription:
        warnings.append("The premium subscription is excluded as non-incremental; set subscription.incremental_for_comparison to true to allocate it to a required card.")
    if expected_withdrawals is not None:
        warnings.append("Withdrawal frequency affects account eligibility only where a documented limit is available; withdrawals that lower daily balances lower actual interest.")

    excluded, results = [], []
    for account in catalog["savings_accounts"]:
        account_reasons = []
        for key, label in (("opening_minimum", "opening minimum"), ("ongoing_minimum", "ongoing minimum"), ("minimum_balance_for_listed_apy", "listed APY tier minimum")):
            required = account.get(key)
            if required is not None and balance < Decimal(str(required)):
                account_reasons.append(f"balance is below the {label} of {required}")
        limit = account.get("monthly_withdrawal_limit")
        if expected_withdrawals is not None and limit is not None and limit != -1 and expected_withdrawals > limit:
            account_reasons.append(f"expected {expected_withdrawals} monthly withdrawals exceeds the documented limit of {limit}")

        for card in catalog["cards"]:
            reasons = account_reasons + card_reasons(card, data)
            card_bonus_value = account["card_bonuses"].get(card["name"])
            if card_bonus_value is None:
                reasons.append("no account-specific card APY bonus is documented in the packaged catalog")
            if reasons:
                excluded.append({"savings_account": account["name"], "credit_card": card["name"], "reasons": reasons})
                continue
            base = Decimal(str(account["base_apy_percent"]))
            card_bonus = Decimal(str(card_bonus_value))
            checking_bonus = highest_checking_boost(boosts, account["name"])
            extra_bonus, labels = additive_bonuses(bonuses, account["name"])
            effective = base + card_bonus + checking_bonus + extra_bonus
            interest = money(balance * effective / Decimal("100"))
            membership_cost = money(subscription_cost * 12) if card.get("requires_premium_subscription") and charge_subscription else Decimal("0")
            costs = money(Decimal(str(card["annual_fee"])) + membership_cost)
            results.append({
                "savings_account": account["name"], "credit_card": card["name"],
                "effective_apy_percent": text(effective), "estimated_interest": text(interest),
                "annual_costs": text(costs), "estimated_net_one_year": text(money(interest - costs)),
                "withdrawal_capacity": withdrawal_detail(account),
                "expected_monthly_withdrawals": expected_withdrawals,
                "components": {"base_apy_percent": text(base), "selected_card_bonus_percent": text(card_bonus), "selected_checking_boost_percent": text(checking_bonus), "other_additive_bonus_percent": text(extra_bonus), "card_annual_fee": text(money(Decimal(str(card["annual_fee"])))), "allocated_membership_cost": text(membership_cost), "other_bonus_labels": labels}
            })
    results.sort(key=lambda row: (Decimal(row["estimated_net_one_year"]), Decimal(row["effective_apy_percent"])), reverse=True)
    if not results:
        warnings.append("No fully documented feasible combination was found; review exclusions and provide only verified missing eligibility.")
    return {"assumptions":{"balance":text(balance),"period":"one year","interest_method":"balance multiplied by effective APY","premium_subscription_cost_is_incremental":charge_subscription,"expected_monthly_withdrawals":expected_withdrawals,"card_bonus_policy":"only the highest applicable card bonus is used; each option contains one selected card"},"ranked_options":results,"excluded":excluded,"warnings":warnings}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}, separators=(",", ":")))
