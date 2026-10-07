#!/usr/bin/env python3
"""Select non-stacking APY benefits and calculate daily-compounded interest.

Reads the JSON schema documented in SKILL.md from stdin and emits JSON to stdout.
Rates are percentages: 3.25 means 3.25%.
"""
import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40
ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")
DAYS_PER_YEAR = Decimal("365")
CENT = Decimal("0.01")


def fail(message):
    raise ValueError(message)


def decimal_value(value, label, nonnegative=True):
    if isinstance(value, bool):
        fail(f"{label} must be numeric, not boolean")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        fail(f"{label} must be numeric")
    if not result.is_finite():
        fail(f"{label} must be finite")
    if nonnegative and result < ZERO:
        fail(f"{label} must be nonnegative")
    return result


def parse_day(value, label):
    if not isinstance(value, str):
        fail(f"{label} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError:
        fail(f"{label} must be YYYY-MM-DD")


def choose_highest(items, rate_key, label):
    """Return the highest eligible candidate; ties use lowest source ID deterministically."""
    if items is None:
        return None, ZERO
    if not isinstance(items, list):
        fail(f"{label} must be a list")

    choices = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            fail(f"{label}[{index}] must be an object")
        eligible = item.get("eligible", False)
        if not isinstance(eligible, bool):
            fail(f"{label}[{index}].eligible must be boolean")
        rate = decimal_value(item.get(rate_key, ZERO), f"{label}[{index}].{rate_key}")
        if eligible:
            source = item.get("source_account_id")
            if not isinstance(source, str) or not source:
                fail(f"{label}[{index}].source_account_id is required for eligible candidates")
            choices.append((rate, source, item))

    if not choices:
        return None, ZERO
    choices.sort(key=lambda choice: (-choice[0], choice[1]))
    rate, _source, candidate = choices[0]
    return candidate, rate


def daily_rate(total_apy_pct, convention):
    annual_rate = total_apy_pct / HUNDRED
    if convention == "effective_apy":
        return (ONE + annual_rate) ** (ONE / DAYS_PER_YEAR) - ONE
    if convention == "nominal_annual_rate":
        return annual_rate / DAYS_PER_YEAR
    fail("rate_convention must be effective_apy or nominal_annual_rate")


def money_as_number(value):
    """JSON numeric output is convenient for downstream banking-tool payload assembly."""
    return float(value)


def calculate_one(record, convention):
    if not isinstance(record, dict):
        fail("each savings entry must be an object")

    account_id = record.get("account_id")
    if not isinstance(account_id, str) or not account_id:
        fail("savings.account_id is required")

    base = decimal_value(record.get("base_apy_pct"), f"{account_id}.base_apy_pct")
    selected_checking, checking_rate = choose_highest(
        record.get("checking_candidates", []),
        "boost_apy_pct",
        f"{account_id}.checking_candidates",
    )
    selected_card, card_rate = choose_highest(
        record.get("card_candidates", []),
        "bonus_apy_pct",
        f"{account_id}.card_candidates",
    )
    other_rate = decimal_value(
        record.get("other_bonus_apy_pct", ZERO), f"{account_id}.other_bonus_apy_pct"
    )
    total_rate = base + checking_rate + card_rate + other_rate
    if total_rate <= ZERO:
        fail(f"{account_id} total APY must be positive")

    balances = record.get("daily_balances")
    if not isinstance(balances, list) or not balances:
        fail(f"{account_id}.daily_balances must be a nonempty list")

    normalized_balances = []
    previous_day = None
    seen_days = set()
    for index, entry in enumerate(balances):
        if not isinstance(entry, dict):
            fail(f"{account_id}.daily_balances[{index}] must be an object")
        current_day = parse_day(
            entry.get("date"), f"{account_id}.daily_balances[{index}].date"
        )
        if current_day in seen_days:
            fail(f"{account_id}.daily_balances contains a duplicate date")
        if previous_day is not None and current_day != previous_day + timedelta(days=1):
            fail(f"{account_id}.daily_balances must contain consecutive calendar days")
        balance = decimal_value(
            entry.get("balance"), f"{account_id}.daily_balances[{index}].balance"
        )
        seen_days.add(current_day)
        previous_day = current_day
        normalized_balances.append((current_day, balance))

    rate_per_day = daily_rate(total_rate, convention)
    accrued_interest = ZERO
    for _day, principal_balance in normalized_balances:
        # The day's eligible principal and all previously accrued interest earn the
        # daily rate. Principal may vary by day; accrued interest remains part of the
        # compounded amount until monthly crediting.
        accrued_interest = accrued_interest + (principal_balance + accrued_interest) * rate_per_day

    expected_rounded = accrued_interest.quantize(CENT, rounding=ROUND_HALF_UP)
    output = {
        "account_id": account_id,
        "days": len(normalized_balances),
        "period_start": normalized_balances[0][0].isoformat(),
        "period_end": normalized_balances[-1][0].isoformat(),
        "selected_checking": None if selected_checking is None else {
            "source_account_id": selected_checking["source_account_id"],
            "boost_apy_pct": money_as_number(checking_rate),
        },
        "selected_card": None if selected_card is None else {
            "source_account_id": selected_card["source_account_id"],
            "bonus_apy_pct": money_as_number(card_rate),
        },
        "apy_components_pct": {
            "base": money_as_number(base),
            "checking": money_as_number(checking_rate),
            "card": money_as_number(card_rate),
            "other": money_as_number(other_rate),
            "total_expected": money_as_number(total_rate),
        },
        "expected_interest_unrounded": str(accrued_interest),
        "expected_interest": money_as_number(expected_rounded),
    }

    if record.get("actual_interest") is not None:
        actual_interest = decimal_value(record["actual_interest"], f"{account_id}.actual_interest")
        difference = (expected_rounded - actual_interest).quantize(CENT, rounding=ROUND_HALF_UP)
        output["actual_interest"] = money_as_number(
            actual_interest.quantize(CENT, rounding=ROUND_HALF_UP)
        )
        output["amount_difference"] = money_as_number(difference)
        output["credit_indicated"] = difference > ZERO

    if record.get("actual_apy_pct") is not None:
        actual_apy = decimal_value(record["actual_apy_pct"], f"{account_id}.actual_apy_pct")
        output["actual_apy_pct"] = money_as_number(actual_apy)

    output["report_ready"] = bool(
        output.get("credit_indicated")
        and "actual_interest" in output
        and "actual_apy_pct" in output
    )
    return output


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            fail("input must be a JSON object")
        convention = payload.get("rate_convention")
        if convention not in ("effective_apy", "nominal_annual_rate"):
            fail("rate_convention must be effective_apy or nominal_annual_rate")
        savings = payload.get("savings")
        if not isinstance(savings, list) or not savings:
            fail("savings must be a nonempty list")

        accounts = [calculate_one(record, convention) for record in savings]
        print(json.dumps({"rate_convention": convention, "accounts": accounts}, indent=2, sort_keys=True))
    except (ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
