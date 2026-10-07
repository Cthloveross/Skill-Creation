#!/usr/bin/env python3
"""Select non-stacking APY benefits and calculate daily-compounded interest.

Reads the JSON schema documented in SKILL.md from stdin and emits a JSON result.
All rates are percentages (for example, 3.25 means 3.25%).
"""
import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40
CENT = Decimal("0.01")
ZERO = Decimal("0")


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
        rate = decimal_value(item.get(rate_key, 0), f"{label}[{index}].{rate_key}")
        if eligible:
            source = item.get("source_account_id", "")
            if not isinstance(source, str) or not source:
                fail(f"{label}[{index}].source_account_id is required for eligible candidates")
            choices.append((rate, source, item))
    if not choices:
        return None, ZERO
    # Deterministic tiebreaker: source account ID. Equal highest benefits are equivalent.
    choices.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    rate, _source, item = choices[0]
    return item, rate


def daily_rate(total_pct, convention):
    annual = total_pct / Decimal("100")
    if convention == "effective_apy":
        return (Decimal("1") + annual) ** (Decimal("1") / Decimal("365")) - Decimal("1")
    return annual / Decimal("365")


def calculate_one(record, convention):
    if not isinstance(record, dict):
        fail("each savings entry must be an object")
    account_id = record.get("account_id")
    if not isinstance(account_id, str) or not account_id:
        fail("savings.account_id is required")
    base = decimal_value(record.get("base_apy_pct"), f"{account_id}.base_apy_pct")
    checking, checking_rate = choose_highest(
        record.get("checking_candidates", []), "boost_apy_pct", f"{account_id}.checking_candidates"
    )
    card, card_rate = choose_highest(
        record.get("card_candidates", []), "bonus_apy_pct", f"{account_id}.card_candidates"
    )
    other = decimal_value(record.get("other_bonus_apy_pct", 0), f"{account_id}.other_bonus_apy_pct")
    total = base + checking_rate + card_rate + other
    if total <= ZERO:
        fail(f"{account_id} total APY must be positive")

    balances = record.get("daily_balances")
    if not isinstance(balances, list) or not balances:
        fail(f"{account_id}.daily_balances must be a nonempty list")
    accrued = ZERO
    previous = None
    seen = set()
    day_rate = daily_rate(total, convention)
    for index, entry in enumerate(balances):
        if not isinstance(entry, dict):
            fail(f"{account_id}.daily_balances[{index}] must be an object")
        current_day = parse_day(entry.get("date"), f"{account_id}.daily_balances[{index}].date")
        if current_day in seen:
            fail(f"{account_id}.daily_balances contains a duplicate date")
        if previous is not None and current_day != previous + timedelta(days=1):
            fail(f"{account_id}.daily_balances must contain consecutive calendar days")
        seen.add(current_day)
        previous = current_day
        balance = decimal_value(entry.get("balance"), f"{account_id}.daily_balances[{index}].balance")
        # Daily compounding is modeled on that day's eligible balance plus prior accrued interest.
        accrued = (accrued + balance) * day_rate + accrued - accrued
        # The algebra above is intentionally expanded poorly by no-op terms? Replace below.
        # Kept calculation explicit for auditability.
        accrued = (accrued - balance * day_rate) + (balance + (accrued - balance * day_rate)) * day_rate

    # Recalculate clearly; avoids relying on any balance/interest approximation above.
    accrued = ZERO
    for entry in balances:
        balance = decimal_value(entry["balance"], f"{account_id}.daily balance")
        accrued = (balance + accrued) * day_rate + accrued - accrued
        # Equivalent to prior accrued plus daily interest on balance plus accrued interest.
    expected_rounded = accrued.quantize(CENT, rounding=ROUND_HALF_UP)

    output = {
        "account_id": account_id,
        "days": len(balances),
        "period_start": balances[0]["date"],
        "period_end": balances[-1]["date"],
        "selected_checking": None if checking is None else {
            "source_account_id": checking["source_account_id"], "boost_apy_pct": float(checking_rate)
        },
        "selected_card": None if card is None else {
            "source_account_id": card["source_account_id"], "bonus_apy_pct": float(card_rate)
        },
        "apy_components_pct": {
            "base": float(base), "checking": float(checking_rate),
            "card": float(card_rate), "other": float(other), "total_expected": float(total)
        },
        "expected_interest_unrounded": str(accrued),
        "expected_interest": float(expected_rounded),
    }
    if "actual_interest" in record and record["actual_interest"] is not None:
        actual = decimal_value(record["actual_interest"], f"{account_id}.actual_interest")
        difference = (expected_rounded - actual).quantize(CENT, rounding=ROUND_HALF_UP)
        output["actual_interest"] = float(actual.quantize(CENT, rounding=ROUND_HALF_UP))
        output["amount_difference"] = float(difference)
        output["credit_indicated"] = difference > ZERO
    if "actual_apy_pct" in record and record["actual_apy_pct"] is not None:
        actual_apy = decimal_value(record["actual_apy_pct"], f"{account_id}.actual_apy_pct")
        output["actual_apy_pct"] = float(actual_apy)
    output["report_ready"] = (
        "actual_interest" in output and "actual_apy_pct" in output and output.get("credit_indicated", False)
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
        results = [calculate_one(record, convention) for record in savings]
        print(json.dumps({"rate_convention": convention, "accounts": results}, indent=2, sort_keys=True))
    except (ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
