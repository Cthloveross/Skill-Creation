#!/usr/bin/env python3
"""Select APY components and calculate daily-compounded interest from complete evidence."""
import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40
ZERO, ONE, HUNDRED, DAYS, CENT = Decimal("0"), Decimal("1"), Decimal("100"), Decimal("365"), Decimal("0.01")


def fail(message):
    raise ValueError(message)


def number(value, label):
    if isinstance(value, bool):
        fail(f"{label} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        fail(f"{label} must be numeric")
    if not result.is_finite() or result < ZERO:
        fail(f"{label} must be a finite nonnegative number")
    return result


def parse_day(value, label):
    if not isinstance(value, str):
        fail(f"{label} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError:
        fail(f"{label} must be YYYY-MM-DD")


def select(candidates, rate_key, label):
    if not isinstance(candidates, list):
        fail(f"{label} must be a list")
    selected = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            fail(f"{label}[{index}] must be an object")
        eligible = candidate.get("eligible", False)
        if not isinstance(eligible, bool):
            fail(f"{label}[{index}].eligible must be boolean")
        rate = number(candidate.get(rate_key, 0), f"{label}[{index}].{rate_key}")
        if eligible:
            account_id = candidate.get("source_account_id")
            if not isinstance(account_id, str) or not account_id:
                fail(f"{label}[{index}].source_account_id is required when eligible")
            selected.append((rate, account_id))
    if not selected:
        return None, ZERO
    selected.sort(key=lambda item: (-item[0], item[1]))
    return selected[0][1], selected[0][0]


def rate_per_day(apy, convention):
    annual = apy / HUNDRED
    if convention == "effective_apy":
        return (ONE + annual) ** (ONE / DAYS) - ONE
    if convention == "nominal_annual_rate":
        return annual / DAYS
    fail("rate_convention must be effective_apy or nominal_annual_rate")


def calculate(record, convention):
    if not isinstance(record, dict):
        fail("each savings entry must be an object")
    account_id = record.get("account_id")
    if not isinstance(account_id, str) or not account_id:
        fail("savings.account_id is required")
    base = number(record.get("base_apy_pct"), f"{account_id}.base_apy_pct")
    checking_id, checking = select(record.get("checking_candidates", []), "boost_apy_pct", f"{account_id}.checking_candidates")
    card_id, card = select(record.get("card_candidates", []), "bonus_apy_pct", f"{account_id}.card_candidates")
    other = number(record.get("other_bonus_apy_pct", 0), f"{account_id}.other_bonus_apy_pct")
    total = base + checking + card + other
    if total <= ZERO:
        fail(f"{account_id} total APY must be positive")

    entries = record.get("daily_balances")
    if not isinstance(entries, list) or not entries:
        fail(f"{account_id}.daily_balances must be a nonempty list")
    balances, prior = [], None
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            fail(f"{account_id}.daily_balances[{index}] must be an object")
        current = parse_day(entry.get("date"), f"{account_id}.daily_balances[{index}].date")
        if prior is not None and current != prior + timedelta(days=1):
            fail(f"{account_id}.daily_balances must contain consecutive unique dates")
        balances.append((current, number(entry.get("balance"), f"{account_id}.daily_balances[{index}].balance")))
        prior = current

    accrued = ZERO
    daily = rate_per_day(total, convention)
    for _day, balance in balances:
        accrued += (balance + accrued) * daily
    expected = accrued.quantize(CENT, rounding=ROUND_HALF_UP)
    output = {
        "account_id": account_id,
        "period_start": balances[0][0].isoformat(), "period_end": balances[-1][0].isoformat(), "days": len(balances),
        "selected_checking": None if checking_id is None else {"source_account_id": checking_id, "boost_apy_pct": float(checking)},
        "selected_card": None if card_id is None else {"source_account_id": card_id, "bonus_apy_pct": float(card)},
        "apy_components_pct": {"base": float(base), "checking": float(checking), "card": float(card), "other": float(other), "total_expected": float(total)},
        "expected_interest_unrounded": str(accrued), "expected_interest": float(expected), "report_ready": False
    }
    if record.get("actual_interest") is not None:
        actual = number(record["actual_interest"], f"{account_id}.actual_interest").quantize(CENT, rounding=ROUND_HALF_UP)
        difference = (expected - actual).quantize(CENT, rounding=ROUND_HALF_UP)
        output.update({"actual_interest": float(actual), "amount_difference": float(difference), "credit_indicated": difference > ZERO})
    if record.get("actual_apy_pct") is not None:
        output["actual_apy_pct"] = float(number(record["actual_apy_pct"], f"{account_id}.actual_apy_pct"))
    output["report_ready"] = bool(output.get("credit_indicated") and "actual_apy_pct" in output)
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
        print(json.dumps({"rate_convention": convention, "accounts": [calculate(item, convention) for item in savings]}, sort_keys=True))
    except (ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
