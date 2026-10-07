#!/usr/bin/env python3
"""Compute one-year savings/card comparison estimates from JSON stdin.

The program never accesses customer data or takes banking actions.  Input and output
are documented in SKILL.md.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
HUNDRED = Decimal("100")
TWELVE = Decimal("12")


def money(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def decimal(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number")
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number")
    if not value.is_finite():
        raise ValueError(f"{field} must be finite")
    return value


def nonnegative(value, field):
    value = decimal(value, field)
    if value < ZERO:
        raise ValueError(f"{field} must be nonnegative")
    return value


def item_name(item, field):
    value = item.get("name")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}.name must be a nonempty string")
    return value.strip()


def eligibility(item, field):
    value = item.get("eligibility_status", "confirmed")
    if value not in {"confirmed", "conditional", "ineligible"}:
        raise ValueError(f"{field}.eligibility_status is invalid")
    return value


def bool_or_default(item, key, default, field):
    value = item.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{field}.{key} must be boolean")
    return value


def reward(card, monthly_spend, category, field):
    """Return annual redeemable reward value.

    rate_unit=percent means a rate such as 1 for 1%.  points_per_dollar means a
    rate such as 1 for one point per dollar and requires point_value.
    """
    rates = card.get("reward_rates", card.get("reward_rates_pct", {}))
    if not isinstance(rates, dict):
        raise ValueError(f"{field}.reward_rates must be an object")
    if category and category in rates:
        rate = nonnegative(rates[category], f"{field}.reward_rates[{category!r}]")
    else:
        rate = nonnegative(card.get("default_reward_rate", card.get("default_reward_rate_pct", 0)),
                           f"{field}.default_reward_rate")
    unit = card.get("reward_rate_unit", "percent")
    annual_spend = monthly_spend * TWELVE
    if unit == "percent":
        return annual_spend * rate / HUNDRED
    if unit == "points_per_dollar":
        point_value = nonnegative(card.get("point_value", "0"), f"{field}.point_value")
        return annual_spend * rate * point_value
    raise ValueError(f"{field}.reward_rate_unit must be percent or points_per_dollar")


def bonus(card, account_name, selected, field):
    if account_name in selected:
        return nonnegative(selected[account_name], f"selected_card_apy_bonus_pct[{account_name!r}]")
    bonuses = card.get("card_apy_bonuses_pct", {})
    if not isinstance(bonuses, dict):
        raise ValueError(f"{field}.card_apy_bonuses_pct must be an object")
    return nonnegative(bonuses.get(account_name, 0), f"{field}.card_apy_bonuses_pct[{account_name!r}]")


def applicable_fee(account, card, balance, account_field, card_field):
    """Return annual maintenance fee, respecting a card-specific waiver threshold."""
    fee = nonnegative(account.get("monthly_maintenance_fee", 0), f"{account_field}.monthly_maintenance_fee")
    if "fee_applies" in account:
        applies = bool_or_default(account, "fee_applies", False, account_field)
    else:
        threshold = account.get("fee_waiver_balance")
        overrides = card.get("fee_waiver_balance_overrides", {})
        if not isinstance(overrides, dict):
            raise ValueError(f"{card_field}.fee_waiver_balance_overrides must be an object")
        if item_name(account, account_field) in overrides:
            threshold = overrides[item_name(account, account_field)]
        applies = threshold is not None and balance < nonnegative(threshold, f"{account_field}.fee_waiver_balance")
    return fee * TWELVE if applies else ZERO, applies


def calculate(request):
    if not isinstance(request, dict):
        raise ValueError("input must be a JSON object")
    balance = nonnegative(request.get("initial_savings_balance"), "initial_savings_balance")
    spend_low = nonnegative(request.get("monthly_spend_low"), "monthly_spend_low")
    spend_high = nonnegative(request.get("monthly_spend_high"), "monthly_spend_high")
    if spend_low > spend_high:
        raise ValueError("monthly_spend_low must not exceed monthly_spend_high")
    accounts, cards = request.get("savings_accounts"), request.get("cards")
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("savings_accounts must be a nonempty array")
    if not isinstance(cards, list) or not cards:
        raise ValueError("cards must be a nonempty array")
    category = request.get("spend_category")
    if category is not None and (not isinstance(category, str) or not category.strip()):
        raise ValueError("spend_category must be a nonempty string when provided")
    selected = request.get("selected_card_apy_bonus_pct", request.get("card_apy_bonus_selection", {}))
    if not isinstance(selected, dict):
        raise ValueError("selected_card_apy_bonus_pct must be an object")

    rows = []
    for ai, account in enumerate(accounts):
        afield = f"savings_accounts[{ai}]"
        aname, astatus = item_name(account, afield), eligibility(account, afield)
        if astatus == "ineligible":
            continue
        base = nonnegative(account.get("base_apy_pct"), f"{afield}.base_apy_pct")
        other = nonnegative(account.get("additional_apy_pct", 0), f"{afield}.additional_apy_pct")
        for ci, card in enumerate(cards):
            cfield = f"cards[{ci}]"
            cname, cstatus = item_name(card, cfield), eligibility(card, cfield)
            if cstatus == "ineligible":
                continue
            apy = base + other + bonus(card, aname, selected, cfield)
            interest = balance * apy / HUNDRED
            maintenance, maintenance_applies = applicable_fee(account, card, balance, afield, cfield)
            annual_fee = nonnegative(card.get("annual_fee", 0), f"{cfield}.annual_fee")
            membership = nonnegative(card.get("required_membership_monthly_fee", 0),
                                     f"{cfield}.required_membership_monthly_fee") * TWELVE
            redeemable = bool_or_default(card, "rewards_redeemable", True, cfield)
            low_rewards = reward(card, spend_low, category, cfield) if redeemable else ZERO
            high_rewards = reward(card, spend_high, category, cfield) if redeemable else ZERO
            fees = maintenance + annual_fee + membership
            row_status = "confirmed" if astatus == cstatus == "confirmed" else "conditional"
            rows.append({
                "savings_account": aname, "card": cname, "eligibility_status": row_status,
                "apy_pct": str(apy), "maintenance_fee_applies": maintenance_applies,
                "components": {
                    "estimated_savings_interest": str(money(interest)),
                    "estimated_rewards_low": str(money(low_rewards)),
                    "estimated_rewards_high": str(money(high_rewards)),
                    "annualized_maintenance_fee": str(money(maintenance)),
                    "card_annual_fee": str(money(annual_fee)),
                    "annualized_required_membership_fee": str(money(membership)),
                    "total_fees": str(money(fees)),
                },
                "net_value_low": str(money(interest + low_rewards - fees)),
                "net_value_high": str(money(interest + high_rewards - fees)),
                "rewards_included": redeemable,
            })
    if not rows:
        raise ValueError("no non-ineligible savings/card combinations were supplied")
    rows.sort(key=lambda r: (Decimal(r["net_value_high"]), Decimal(r["net_value_low"])), reverse=True)
    for rank, row in enumerate(rows, 1):
        row["rank_by_high_spend_estimate"] = rank
    confirmed = [row for row in rows if row["eligibility_status"] == "confirmed"]
    return {"ok": True,
            "assumptions": {"balance_is_held_for_one_year": True,
                            "rewards_are_based_on_eligible_posted_spend": True,
                            "apr_interest_is_not_estimated": True},
            "best_confirmed_combination": confirmed[0] if confirmed else None,
            "combinations": rows}


def main():
    try:
        print(json.dumps(calculate(json.load(sys.stdin)), separators=(",", ":")))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))

if __name__ == "__main__":
    main()
