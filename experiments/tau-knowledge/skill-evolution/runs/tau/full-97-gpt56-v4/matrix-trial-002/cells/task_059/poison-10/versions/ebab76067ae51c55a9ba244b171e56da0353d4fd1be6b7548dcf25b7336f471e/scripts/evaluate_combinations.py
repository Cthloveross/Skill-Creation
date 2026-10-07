#!/usr/bin/env python3
"""Calculate comparable first-period values for documented banking product pairs.

Reads one JSON object from stdin using the schema in SKILL.md and writes one JSON
object to stdout. Monetary inputs may be JSON numbers or decimal strings. APY is
an annual percentage yield, so interest for `days` is calculated as:
    balance * ((1 + APY / 100) ** (days / 365) - 1)
All output monetary values are decimal strings rounded to cents.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40
CENT = Decimal("0.01")
YEAR = Decimal("365")
VALID_BONUS_STATUSES = {"eligible", "conditional", "ineligible"}


def decimal_value(value, field, *, nonnegative=True):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be a decimal number")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    if nonnegative and result < 0:
        raise ValueError(f"{field} must not be negative")
    return result


def money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), "f")


def required_text(record, field):
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value.strip()


def evaluate(candidate, balance, days, annual_spend):
    savings_name = required_text(candidate, "savings_name")
    card_name = required_text(candidate, "card_name")
    apy = decimal_value(candidate.get("effective_apy"), "effective_apy")
    monthly_fee = decimal_value(candidate.get("monthly_savings_fee", 0), "monthly_savings_fee")
    annual_fee = decimal_value(candidate.get("annual_card_fee", 0), "annual_card_fee")
    reward_rate = decimal_value(candidate.get("reward_value_per_dollar", 0), "reward_value_per_dollar")
    welcome_value = decimal_value(candidate.get("welcome_bonus_value", 0), "welcome_bonus_value")
    status = candidate.get("welcome_bonus_status", "ineligible")
    if status not in VALID_BONUS_STATUSES:
        raise ValueError("welcome_bonus_status must be eligible, conditional, or ineligible")
    notes = candidate.get("notes", [])
    if not isinstance(notes, list) or not all(isinstance(note, str) for note in notes):
        raise ValueError("notes must be an array of strings")

    # APY is an annual yield, so a full 365-day period has exact interest
    # balance * APY / 100. Other periods use the equivalent annual-growth ratio.
    if days == 365:
        interest = balance * apy / Decimal("100")
    else:
        growth = Decimal(str((1.0 + float(apy) / 100.0) ** (days / 365.0)))
        interest = balance * (growth - Decimal("1"))
    savings_fees = monthly_fee * Decimal("12") * Decimal(days) / YEAR
    rewards = annual_spend * reward_rate * Decimal(days) / YEAR
    included_welcome = welcome_value if status == "eligible" else Decimal("0")
    conditional_welcome = welcome_value if status == "conditional" else Decimal("0")
    net = interest - savings_fees + rewards - annual_fee * Decimal(days) / YEAR + included_welcome

    return {
        "savings_name": savings_name,
        "card_name": card_name,
        "effective_apy_percent": str(apy),
        "savings_interest": money(interest),
        "savings_fees": money(savings_fees),
        "card_rewards": money(rewards),
        "annual_card_fee_prorated": money(annual_fee * Decimal(days) / YEAR),
        "included_welcome_bonus": money(included_welcome),
        "conditional_welcome_bonus_not_included": money(conditional_welcome),
        "net_value_excluding_conditional_bonus": money(net),
        "welcome_bonus_status": status,
        "notes": notes,
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        balance = decimal_value(payload.get("balance"), "balance")
        annual_spend = decimal_value(payload.get("annual_card_spend"), "annual_card_spend")
        days_value = payload.get("days", 365)
        if isinstance(days_value, bool):
            raise ValueError("days must be a positive integer")
        if isinstance(days_value, int):
            days = days_value
        elif isinstance(days_value, str) and days_value.strip().isdigit():
            days = int(days_value.strip())
        else:
            raise ValueError("days must be a positive integer")
        if days <= 0:
            raise ValueError("days must be a positive integer")
        candidates = payload.get("candidates")
        if not isinstance(candidates, list):
            raise ValueError("candidates must be an array")
    except (ValueError, json.JSONDecodeError) as exc:
        json.dump({"results": [], "errors": [{"input": str(exc)}]}, sys.stdout)
        return

    results = []
    errors = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            errors.append({"candidate_index": index, "error": "candidate must be an object"})
            continue
        try:
            results.append(evaluate(candidate, balance, days, annual_spend))
        except ValueError as exc:
            errors.append({"candidate_index": index, "error": str(exc)})

    results.sort(key=lambda item: Decimal(item["net_value_excluding_conditional_bonus"]), reverse=True)
    json.dump(
        {
            "comparison_period_days": days,
            "results": results,
            "errors": errors,
            "method_note": "Totals are estimates from supplied documented terms; conditional welcome bonuses are not included in net value.",
        },
        sys.stdout,
        separators=(",", ":"),
    )


if __name__ == "__main__":
    main()
