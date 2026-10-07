#!/usr/bin/env python3
"""Compare documented savings/card net-yield options from JSON stdin.

This helper is intentionally data-driven: callers supply product terms extracted from
current task documents. It does not retrieve customer data or perform banking actions.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40

VALID_ELIGIBILITY = {"eligible", "conditional", "unknown", "ineligible"}
ZERO = Decimal("0")
HUNDRED = Decimal("100")
DAYS_PER_YEAR = Decimal("365")
MONEY = Decimal("0.01")


def decimal_value(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number, not a boolean")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a valid number")
    if not number.is_finite():
        raise ValueError(f"{field} must be finite")
    return number


def nonnegative(value, field):
    number = decimal_value(value, field)
    if number < ZERO:
        raise ValueError(f"{field} must be nonnegative")
    return number


def currency(value):
    return float(value.quantize(MONEY, rounding=ROUND_HALF_UP))


def percent(value, field):
    return nonnegative(value, field)


def normalize_status(value, field):
    if value not in VALID_ELIGIBILITY:
        allowed = ", ".join(sorted(VALID_ELIGIBILITY))
        raise ValueError(f"{field} must be one of: {allowed}")
    return value


def combined_status(savings_status, card_status):
    if "ineligible" in (savings_status, card_status):
        return "ineligible"
    if "unknown" in (savings_status, card_status):
        return "conditional"
    if "conditional" in (savings_status, card_status):
        return "conditional"
    return "eligible"


def required_text(item, field):
    value = item.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value.strip()


def evaluate_option(option, card, balance, months, withdrawals):
    savings_name = required_text(option, "savings_name")
    card_name = required_text(card, "card_name")
    base_apy = percent(option["base_apy_pct"], "base_apy_pct")
    checking_boost = percent(option.get("checking_boost_pct", 0), "checking_boost_pct")
    relationship_bonus = percent(
        option.get("relationship_bonus_pct", 0), "relationship_bonus_pct"
    )
    card_bonus = percent(card.get("bonus_apy_pct", 0), "bonus_apy_pct")
    opening_minimum = nonnegative(option["opening_minimum"], "opening_minimum")
    ongoing_minimum = nonnegative(option["ongoing_minimum"], "ongoing_minimum")
    savings_fee = nonnegative(option.get("savings_annual_fee", 0), "savings_annual_fee")
    card_fee = nonnegative(card.get("annual_fee", 0), "annual_fee")
    savings_status = normalize_status(option["savings_eligibility"], "savings_eligibility")
    card_status = normalize_status(card["eligibility"], "eligibility")

    warnings = []
    if balance < opening_minimum:
        warnings.append("Planned balance is below the documented opening minimum.")
        savings_status = "ineligible"
    if balance < ongoing_minimum:
        warnings.append("Planned balance is below the documented ongoing minimum.")
        savings_status = "ineligible"

    withdrawal_limit = option.get("withdrawal_limit")
    if withdrawal_limit is None:
        warnings.append("No withdrawal limit was supplied; access suitability is unconfirmed.")
    else:
        if isinstance(withdrawal_limit, bool) or not isinstance(withdrawal_limit, int):
            raise ValueError("withdrawal_limit must be an integer or null")
        if withdrawal_limit == -1:
            warnings.append("Withdrawal limit is treated as unlimited only because input uses -1.")
        elif withdrawal_limit < 0:
            raise ValueError("withdrawal_limit must be nonnegative, -1, or null")
        elif withdrawals > withdrawal_limit:
            warnings.append("Expected monthly withdrawals exceed the documented limit.")
            savings_status = "ineligible"

    status = combined_status(savings_status, card_status)
    effective_apy = base_apy + checking_boost + relationship_bonus + card_bonus
    days = Decimal("365") * months / Decimal("12")
    growth = (Decimal("1") + effective_apy / HUNDRED) ** (days / DAYS_PER_YEAR)
    gross_interest = balance * (growth - Decimal("1"))
    annual_fees = (savings_fee + card_fee) * months / Decimal("12")
    net_earnings = gross_interest - annual_fees

    if card_status in {"conditional", "unknown"}:
        warnings.append("Card eligibility is not confirmed; card bonus and fee are conditional.")
    if option["savings_eligibility"] in {"conditional", "unknown"}:
        warnings.append("Savings eligibility is not confirmed.")

    return {
        "savings_name": savings_name,
        "card_name": card_name,
        "status": status,
        "effective_apy_pct": float(effective_apy),
        "gross_interest": currency(gross_interest),
        "annual_fees": currency(annual_fees),
        "net_earnings": currency(net_earnings),
        "warnings": warnings,
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        balance = nonnegative(payload["balance"], "balance")
        months = nonnegative(payload.get("months", 12), "months")
        if months <= ZERO:
            raise ValueError("months must be greater than zero")
        withdrawals = payload.get("withdrawals_per_month", 0)
        if isinstance(withdrawals, bool) or not isinstance(withdrawals, int) or withdrawals < 0:
            raise ValueError("withdrawals_per_month must be a nonnegative integer")
        options = payload.get("options")
        if not isinstance(options, list) or not options:
            raise ValueError("options must be a nonempty array")

        results = []
        for option in options:
            if not isinstance(option, dict):
                raise ValueError("each option must be an object")
            cards = option.get("cards")
            if not isinstance(cards, list) or not cards:
                raise ValueError("each option must contain a nonempty cards array")
            for card in cards:
                if not isinstance(card, dict):
                    raise ValueError("each card must be an object")
                results.append(evaluate_option(option, card, balance, months, withdrawals))

        status_order = {"eligible": 0, "conditional": 1, "ineligible": 2}
        results.sort(key=lambda r: (status_order[r["status"]], -r["net_earnings"], r["savings_name"], r["card_name"]))
        eligible = [r for r in results if r["status"] == "eligible"]
        conditional = [r for r in results if r["status"] == "conditional"]
        output = {
            "assumptions": [
                "The balance remains stable and eligible throughout the modeled period.",
                "APY is treated as an effective annual yield and modeled with daily compounding.",
                "Only supplied annual fees are subtracted; transaction, maintenance, and withdrawal fees are excluded unless included as annual fees.",
                "Each result evaluates one card option; do not add bonuses across multiple cards.",
            ],
            "results": results,
            "best_eligible": eligible[0] if eligible else None,
            "best_conditional": conditional[0] if conditional else None,
        }
        print(json.dumps(output, separators=(",", ":"), ensure_ascii=False))
    except (KeyError, ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
