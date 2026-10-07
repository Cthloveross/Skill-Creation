#!/usr/bin/env python3
"""Calculate comparable one-year net estimates for savings/card combinations.

Input and output schemas are documented in SKILL.md. This utility only performs
arithmetic on explicitly supplied product terms; it does not access accounts or
perform banking actions.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
HUNDRED = Decimal("100")
TWELVE = Decimal("12")


def money(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def number(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def nonnegative(value, field):
    result = number(value, field)
    if result < ZERO:
        raise ValueError(f"{field} must be nonnegative")
    return result


def status(item, field):
    value = item.get("eligibility_status", "confirmed")
    if value not in {"confirmed", "conditional", "ineligible"}:
        raise ValueError(f"{field}.eligibility_status is invalid")
    return value


def name(item, field):
    value = item.get("name")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}.name must be a nonempty string")
    return value.strip()


def rate_for_spend(card, category, field):
    rates = card.get("reward_rates_pct", {})
    if not isinstance(rates, dict):
        raise ValueError(f"{field}.reward_rates_pct must be an object")
    if category is not None and category in rates:
        return nonnegative(rates[category], f"{field}.reward_rates_pct[{category!r}]")
    return nonnegative(card.get("default_reward_rate_pct", 0), f"{field}.default_reward_rate_pct")


def card_bonus(card, savings_name, selection, field):
    if savings_name in selection:
        return nonnegative(selection[savings_name], f"card_apy_bonus_selection[{savings_name!r}]")
    bonuses = card.get("card_apy_bonuses_pct", {})
    if not isinstance(bonuses, dict):
        raise ValueError(f"{field}.card_apy_bonuses_pct must be an object")
    return nonnegative(bonuses.get(savings_name, 0), f"{field}.card_apy_bonuses_pct[{savings_name!r}]")


def calculate(request):
    balance = nonnegative(request.get("initial_savings_balance"), "initial_savings_balance")
    low_spend = nonnegative(request.get("monthly_spend_low"), "monthly_spend_low")
    high_spend = nonnegative(request.get("monthly_spend_high"), "monthly_spend_high")
    if low_spend > high_spend:
        raise ValueError("monthly_spend_low must not exceed monthly_spend_high")
    accounts = request.get("savings_accounts")
    cards = request.get("cards")
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("savings_accounts must be a nonempty array")
    if not isinstance(cards, list) or not cards:
        raise ValueError("cards must be a nonempty array")
    category = request.get("spend_category")
    if category is not None and (not isinstance(category, str) or not category.strip()):
        raise ValueError("spend_category must be a nonempty string when provided")
    selection = request.get("card_apy_bonus_selection", {})
    if not isinstance(selection, dict):
        raise ValueError("card_apy_bonus_selection must be an object")

    rows = []
    for account_index, account in enumerate(accounts):
        account_field = f"savings_accounts[{account_index}]"
        account_name = name(account, account_field)
        account_status = status(account, account_field)
        if account_status == "ineligible":
            continue
        base_apy = nonnegative(account.get("base_apy_pct"), f"{account_field}.base_apy_pct")
        other_apy = nonnegative(account.get("additional_apy_pct", 0), f"{account_field}.additional_apy_pct")
        maintenance_monthly = nonnegative(account.get("monthly_maintenance_fee"), f"{account_field}.monthly_maintenance_fee")
        maintenance_fee = maintenance_monthly * TWELVE if bool(account.get("fee_applies", False)) else ZERO

        for card_index, card in enumerate(cards):
            card_field = f"cards[{card_index}]"
            card_name = name(card, card_field)
            card_status = status(card, card_field)
            if card_status == "ineligible":
                continue
            bonus = card_bonus(card, account_name, selection, card_field)
            total_apy = base_apy + other_apy + bonus
            interest = balance * total_apy / HUNDRED
            annual_fee = nonnegative(card.get("annual_fee", 0), f"{card_field}.annual_fee")
            membership_fee = nonnegative(card.get("required_membership_monthly_fee", 0), f"{card_field}.required_membership_monthly_fee") * TWELVE
            reward_rate = rate_for_spend(card, category, card_field)
            redeemable = bool(card.get("rewards_redeemable", True))
            reward_value = nonnegative(card.get("reward_value_per_unit", 1), f"{card_field}.reward_value_per_unit")
            # Percent rates normally yield cash dollars. reward_value_per_unit supports
            # points-per-dollar representations supplied by the caller.
            if redeemable:
                rewards_low = low_spend * TWELVE * reward_rate / HUNDRED * reward_value
                rewards_high = high_spend * TWELVE * reward_rate / HUNDRED * reward_value
            else:
                rewards_low = ZERO
                rewards_high = ZERO
            fees = maintenance_fee + annual_fee + membership_fee
            certainty = "confirmed" if account_status == card_status == "confirmed" else "conditional"
            rows.append({
                "savings_account": account_name,
                "card": card_name,
                "eligibility_status": certainty,
                "apy_pct": str(total_apy),
                "components": {
                    "estimated_savings_interest": str(money(interest)),
                    "estimated_rewards_low": str(money(rewards_low)),
                    "estimated_rewards_high": str(money(rewards_high)),
                    "annualized_maintenance_fee": str(money(maintenance_fee)),
                    "card_annual_fee": str(money(annual_fee)),
                    "annualized_required_membership_fee": str(money(membership_fee)),
                    "total_fees": str(money(fees)),
                },
                "net_value_low": str(money(interest + rewards_low - fees)),
                "net_value_high": str(money(interest + rewards_high - fees)),
                "rewards_included": redeemable,
            })
    if not rows:
        raise ValueError("no non-ineligible savings/card combinations were supplied")
    rows.sort(key=lambda row: (Decimal(row["net_value_high"]), Decimal(row["net_value_low"])), reverse=True)
    for index, row in enumerate(rows, 1):
        row["rank_by_high_spend_estimate"] = index
    confirmed = [r for r in rows if r["eligibility_status"] == "confirmed"]
    return {
        "ok": True,
        "assumptions": {
            "balance_is_held_for_one_year": True,
            "rewards_are_based_on_eligible_posted_spend": True,
            "maintenance_fees_are_included_only_when_fee_applies_is_true": True,
            "apr_interest_is_not_estimated": True,
        },
        "best_confirmed_combination": confirmed[0] if confirmed else None,
        "combinations": rows,
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(calculate(payload), separators=(",", ":")))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))


if __name__ == "__main__":
    main()
