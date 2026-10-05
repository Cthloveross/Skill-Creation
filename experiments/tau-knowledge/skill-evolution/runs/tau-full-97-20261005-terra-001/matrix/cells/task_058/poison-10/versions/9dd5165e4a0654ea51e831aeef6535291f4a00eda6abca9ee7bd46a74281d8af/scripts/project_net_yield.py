#!/usr/bin/env python3
"""Rank verified savings/card combinations by projected net yield.

Reads one JSON object from stdin and writes one JSON object to stdout. See
SKILL.md for the supported schema. This program performs no external I/O.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
HUNDRED = Decimal("100")


def money(value):
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def decimal_value(value, field, errors, nonnegative=True):
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f"{field} must be numeric")
        return None
    if not parsed.is_finite():
        errors.append(f"{field} must be finite")
        return None
    if nonnegative and parsed < 0:
        errors.append(f"{field} cannot be negative")
        return None
    return parsed


def number_list(value, field, errors):
    if not isinstance(value, list):
        errors.append(f"{field} must be a list")
        return []
    result = []
    for index, item in enumerate(value):
        parsed = decimal_value(item, f"{field}[{index}]", errors)
        if parsed is not None:
            result.append(parsed)
    return result


def analyze_option(option, balance, months):
    errors = []
    if not isinstance(option, dict):
        return {"label": "unnamed option", "reasons": ["option must be an object"]}

    label = option.get("label", "unnamed option")
    if not isinstance(label, str) or not label.strip():
        label = "unnamed option"
        errors.append("label must be a nonempty string")

    account = option.get("savings_account")
    if not isinstance(account, str) or not account.strip().endswith("Account"):
        errors.append("savings_account must be the full official name ending in 'Account'")

    base_apy = decimal_value(option.get("base_apy"), "base_apy", errors)
    opening_minimum = decimal_value(option.get("minimum_opening_deposit"), "minimum_opening_deposit", errors)
    ongoing_minimum = decimal_value(option.get("minimum_ongoing_balance"), "minimum_ongoing_balance", errors)
    card_bonuses = number_list(option.get("card_apy_bonuses", []), "card_apy_bonuses", errors)
    checking_boosts = number_list(option.get("checking_apy_boosts", []), "checking_apy_boosts", errors)
    other_bonuses = number_list(option.get("other_stackable_apy_bonuses", []), "other_stackable_apy_bonuses", errors)

    if option.get("eligibility_confirmed") is not True:
        errors.append("product and bonus eligibility is not confirmed")

    fees = option.get("annual_fees", [])
    fee_total = Decimal("0")
    if not isinstance(fees, list):
        errors.append("annual_fees must be a list")
    else:
        for index, fee in enumerate(fees):
            if not isinstance(fee, dict):
                errors.append(f"annual_fees[{index}] must be an object")
                continue
            amount = decimal_value(fee.get("amount"), f"annual_fees[{index}].amount", errors)
            product = fee.get("product")
            if not isinstance(product, str) or not product.strip():
                errors.append(f"annual_fees[{index}].product must be a nonempty string")
            if amount is not None:
                fee_total += amount

    if opening_minimum is not None and balance < opening_minimum:
        errors.append("projected balance is below the minimum opening deposit")
    if ongoing_minimum is not None and balance < ongoing_minimum:
        errors.append("projected balance is below the ongoing minimum balance")

    if errors:
        return {"label": label, "reasons": errors}

    # Per policy, card bonuses and checking boosts each select one maximum;
    # separately documented stackable bonuses are added.
    selected_card_bonus = max(card_bonuses, default=Decimal("0"))
    selected_checking_boost = max(checking_boosts, default=Decimal("0"))
    effective_apy = base_apy + selected_card_bonus + selected_checking_boost + sum(other_bonuses, Decimal("0"))

    # APY is an annual yield. For a fractional holding period, use the
    # corresponding fractional annual growth; Decimal avoids currency drift.
    if months == Decimal("12"):
        gross_interest = balance * (effective_apy / HUNDRED)
    elif months == Decimal("0"):
        gross_interest = Decimal("0")
    else:
        growth = (1.0 + float(effective_apy / HUNDRED)) ** float(months / Decimal("12")) - 1.0
        gross_interest = balance * Decimal(str(growth))
    net_earnings = gross_interest - fee_total

    return {
        "label": label,
        "savings_account": account,
        "base_apy_percent": str(base_apy),
        "selected_card_bonus_percent": str(selected_card_bonus),
        "selected_checking_boost_percent": str(selected_checking_boost),
        "other_stackable_bonus_percent": str(sum(other_bonuses, Decimal("0"))),
        "effective_apy_percent": str(effective_apy),
        "gross_projected_interest": money(gross_interest),
        "annual_fees": money(fee_total),
        "projected_net_earnings": money(net_earnings),
        "assumptions": [
            "Balance remains stable for the stated holding period.",
            "Only the highest applicable credit-card bonus and highest applicable checking boost were used.",
            "All separately supplied stackable bonuses remain eligible."
        ],
        "_sort_net": net_earnings
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"valid": False, "errors": [f"invalid JSON: {exc.msg}"]}))
        return

    if not isinstance(payload, dict):
        print(json.dumps({"valid": False, "errors": ["input must be a JSON object"]}))
        return

    errors = []
    balance = decimal_value(payload.get("balance"), "balance", errors)
    months = decimal_value(payload.get("months_held", 12), "months_held", errors)
    options = payload.get("options")
    if months is not None and (months < 0 or months > 12):
        errors.append("months_held must be between 0 and 12")
    if not isinstance(options, list) or not options:
        errors.append("options must be a nonempty list")

    if errors:
        print(json.dumps({"valid": False, "errors": errors}))
        return

    eligible = []
    excluded = []
    for option in options:
        result = analyze_option(option, balance, months)
        if "reasons" in result:
            excluded.append(result)
        else:
            eligible.append(result)

    eligible.sort(key=lambda item: item["_sort_net"], reverse=True)
    for item in eligible:
        del item["_sort_net"]

    print(json.dumps({
        "valid": True,
        "balance": money(balance),
        "months_held": str(months),
        "ranked_eligible_options": eligible,
        "ineligible_or_invalid_options": excluded
    }, indent=2))


if __name__ == "__main__":
    main()
