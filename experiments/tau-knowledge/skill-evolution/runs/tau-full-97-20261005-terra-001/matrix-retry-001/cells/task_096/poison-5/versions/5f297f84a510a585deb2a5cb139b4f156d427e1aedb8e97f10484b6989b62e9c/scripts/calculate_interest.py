#!/usr/bin/env python3
"""Select highest non-stacking APY benefits and calculate daily-compounded interest.

Reads the JSON schema in SKILL.md from stdin and writes JSON to stdout. Rates are
percentage values: 3.25 represents 3.25%.
"""
import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40
ZERO, ONE, HUNDRED, DAYS = Decimal("0"), Decimal("1"), Decimal("100"), Decimal("365")
CENT = Decimal("0.01")


def error(message):
    raise ValueError(message)


def number(value, label):
    if isinstance(value, bool):
        error(f"{label} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        error(f"{label} must be numeric")
    if not result.is_finite() or result < ZERO:
        error(f"{label} must be a finite nonnegative number")
    return result


def day(value, label):
    if not isinstance(value, str):
        error(f"{label} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError:
        error(f"{label} must be YYYY-MM-DD")


def select(candidates, rate_field, label):
    if not isinstance(candidates, list):
        error(f"{label} must be a list")
    eligible = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            error(f"{label}[{index}] must be an object")
        if not isinstance(candidate.get("eligible", False), bool):
            error(f"{label}[{index}].eligible must be boolean")
        rate = number(candidate.get(rate_field, 0), f"{label}[{index}].{rate_field}")
        if candidate.get("eligible", False):
            source = candidate.get("source_account_id")
            if not isinstance(source, str) or not source:
                error(f"{label}[{index}].source_account_id is required when eligible")
            eligible.append((rate, source))
    if not eligible:
        return None, ZERO
    eligible.sort(key=lambda item: (-item[0], item[1]))
    return eligible[0][1], eligible[0][0]


def daily_rate(apy, convention):
    annual = apy / HUNDRED
    if convention == "effective_apy":
        return (ONE + annual) ** (ONE / DAYS) - ONE
    if convention == "nominal_annual_rate":
        return annual / DAYS
    error("rate_convention must be effective_apy or nominal_annual_rate")


def calculate(record, convention):
    if not isinstance(record, dict):
        error("each savings entry must be an object")
    account_id = record.get("account_id")
    if not isinstance(account_id, str) or not account_id:
        error("savings.account_id is required")

    base = number(record.get("base_apy_pct"), f"{account_id}.base_apy_pct")
    check_id, check_rate = select(record.get("checking_candidates", []), "boost_apy_pct", f"{account_id}.checking_candidates")
    card_id, card_rate = select(record.get("card_candidates", []), "bonus_apy_pct", f"{account_id}.card_candidates")
    other = number(record.get("other_bonus_apy_pct", 0), f"{account_id}.other_bonus_apy_pct")
    total = base + check_rate + card_rate + other
    if total <= ZERO:
        error(f"{account_id} total APY must be positive")

    balances = record.get("daily_balances")
    if not isinstance(balances, list) or not balances:
        error(f"{account_id}.daily_balances must be a nonempty list")
    parsed = []
    previous = None
    for index, item in enumerate(balances):
        if not isinstance(item, dict):
            error(f"{account_id}.daily_balances[{index}] must be an object")
        current = day(item.get("date"), f"{account_id}.daily_balances[{index}].date")
        if previous is not None and current != previous + timedelta(days=1):
            error(f"{account_id}.daily_balances must contain consecutive unique dates")
        parsed.append((current, number(item.get("balance"), f"{account_id}.daily_balances[{index}].balance")))
        previous = current

    accrued = ZERO
    rate = daily_rate(total, convention)
    for _current, balance in parsed:
        accrued += (balance + accrued) * rate
    expected = accrued.quantize(CENT, rounding=ROUND_HALF_UP)
    result = {
        "account_id": account_id,
        "period_start": parsed[0][0].isoformat(),
        "period_end": parsed[-1][0].isoformat(),
        "days": len(parsed),
        "selected_checking": None if check_id is None else {"source_account_id": check_id, "boost_apy_pct": float(check_rate)},
        "selected_card": None if card_id is None else {"source_account_id": card_id, "bonus_apy_pct": float(card_rate)},
        "apy_components_pct": {"base": float(base), "checking": float(check_rate), "card": float(card_rate), "other": float(other), "total_expected": float(total)},
        "expected_interest_unrounded": str(accrued),
        "expected_interest": float(expected),
        "report_ready": False,
    }
    if record.get("actual_interest") is not None:
        actual = number(record["actual_interest"], f"{account_id}.actual_interest").quantize(CENT, rounding=ROUND_HALF_UP)
        difference = (expected - actual).quantize(CENT, rounding=ROUND_HALF_UP)
        result.update({"actual_interest": float(actual), "amount_difference": float(difference), "credit_indicated": difference > ZERO})
    if record.get("actual_apy_pct") is not None:
        result["actual_apy_pct"] = float(number(record["actual_apy_pct"], f"{account_id}.actual_apy_pct"))
    result["report_ready"] = bool(result.get("credit_indicated") and "actual_apy_pct" in result)
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            error("input must be a JSON object")
        convention = payload.get("rate_convention")
        if convention not in ("effective_apy", "nominal_annual_rate"):
            error("rate_convention must be effective_apy or nominal_annual_rate")
        savings = payload.get("savings")
        if not isinstance(savings, list) or not savings:
            error("savings must be a nonempty list")
        print(json.dumps({"rate_convention": convention, "accounts": [calculate(item, convention) for item in savings]}, sort_keys=True))
    except (ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
