#!/usr/bin/env python3
"""Compare supplied savings-account and card alternatives from JSON stdin.

The caller supplies facts extracted from current product documents. This script performs
no retrieval and no banking action. It validates calculation inputs and returns auditable
components for a customer-facing recommendation.
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
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field} must be a valid number")
    if not number.is_finite():
        raise ValueError(f"{field} must be finite")
    return number


def nonnegative(value, field):
    number = decimal_value(value, field)
    if number < ZERO:
        raise ValueError(f"{field} must be nonnegative")
    return number


def percent(value, field):
    return nonnegative(value, field)


def currency(value):
    return float(value.quantize(MONEY, rounding=ROUND_HALF_UP))


def required_text(item, field):
    value = item.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value.strip()


def normalize_status(value, field):
    if value not in VALID_ELIGIBILITY:
        raise ValueError(
            f"{field} must be one of: {', '.join(sorted(VALID_ELIGIBILITY))}"
        )
    return value


def combined_status(savings_status, card_status):
    if "ineligible" in (savings_status, card_status):
        return "ineligible"
    if "conditional" in (savings_status, card_status) or "unknown" in (
        savings_status,
        card_status,
    ):
        return "conditional"
    return "eligible"


def withdrawal_fit(limit, withdrawals):
    if limit is None:
        return "unconfirmed"
    if limit == -1:
        return "within_limit"
    return "within_limit" if withdrawals <= limit else "exceeds_limit"


def evaluate_option(option, card, balance, months, withdrawals, replenished):
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

    limit = option.get("withdrawal_limit")
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("withdrawal_limit must be an integer, -1, or null")
        if limit < -1:
            raise ValueError("withdrawal_limit must be nonnegative, -1, or null")

    warnings = []
    if balance < opening_minimum:
        warnings.append("Planned balance is below the documented opening minimum.")
        savings_status = "ineligible"
    if balance < ongoing_minimum:
        warnings.append("Planned balance is below the documented ongoing minimum.")
        savings_status = "ineligible"

    fit = withdrawal_fit(limit, withdrawals)
    if fit == "unconfirmed":
        warnings.append("No withdrawal limit was supplied; access suitability is unconfirmed.")
    elif fit == "exceeds_limit":
        warnings.append("Expected monthly withdrawals exceed the documented limit.")
        savings_status = "ineligible"
    elif limit == -1:
        warnings.append("Unlimited withdrawals rely on supplied evidence defining -1 as unlimited.")

    if not replenished:
        warnings.append(
            "Stable-balance earnings are only illustrative because withdrawals are not replenished."
        )
    if card_status in {"conditional", "unknown"}:
        warnings.append("Card eligibility, approval, bonus, and fee treatment are conditional.")
    if savings_status in {"conditional", "unknown"}:
        warnings.append("Savings-account eligibility is not confirmed.")

    effective_apy = base_apy + checking_boost + relationship_bonus + card_bonus
    days = DAYS_PER_YEAR * months / Decimal("12")
    growth = (Decimal("1") + effective_apy / HUNDRED) ** (days / DAYS_PER_YEAR)
    gross_interest = balance * (growth - Decimal("1"))
    annual_fees = (savings_fee + card_fee) * months / Decimal("12")
    net_earnings = gross_interest - annual_fees

    return {
        "savings_name": savings_name,
        "card_name": card_name,
        "status": combined_status(savings_status, card_status),
        "rate_components_pct": {
            "base_apy": float(base_apy),
            "checking_boost": float(checking_boost),
            "relationship_bonus": float(relationship_bonus),
            "card_bonus": float(card_bonus),
            "effective_apy": float(effective_apy),
        },
        "balance": float(balance),
        "opening_minimum": float(opening_minimum),
        "ongoing_minimum": float(ongoing_minimum),
        "balance_meets_opening_minimum": balance >= opening_minimum,
        "balance_meets_ongoing_minimum": balance >= ongoing_minimum,
        "withdrawals_per_month": withdrawals,
        "withdrawal_limit": limit,
        "withdrawal_fit": fit,
        "gross_interest": currency(gross_interest),
        "savings_annual_fee": currency(savings_fee * months / Decimal("12")),
        "card_annual_fee": currency(card_fee * months / Decimal("12")),
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
        replenished = payload.get("balance_is_replenished", True)
        if not isinstance(replenished, bool):
            raise ValueError("balance_is_replenished must be a boolean")
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
                results.append(
                    evaluate_option(
                        option, card, balance, months, withdrawals, replenished
                    )
                )

        status_order = {"eligible": 0, "conditional": 1, "ineligible": 2}
        results.sort(
            key=lambda item: (
                status_order[item["status"]],
                -item["net_earnings"],
                item["savings_name"],
                item["card_name"],
            )
        )
        eligible = [item for item in results if item["status"] == "eligible"]
        conditional = [item for item in results if item["status"] == "conditional"]
        output = {
            "assumptions": [
                "APY is treated as an effective annual yield and modeled using daily compounding.",
                "Only supplied annual fees are subtracted.",
                "Each result evaluates one card alternative; card bonuses must not be added across cards.",
                "Transaction, maintenance, withdrawal, and other fees are excluded unless supplied as applicable annual fees.",
                (
                    "Balance is modeled as remaining near the stated amount because replenishment was supplied."
                    if replenished
                    else "The stable-balance calculation is illustrative because replenishment was not supplied."
                ),
            ],
            "results": results,
            "best_eligible": eligible[0] if eligible else None,
            "best_conditional": conditional[0] if conditional else None,
        }
        print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
    except (KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
