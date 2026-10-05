#!/usr/bin/env python3
"""Calculate an evidenced Silver Account interest cycle from JSON stdin.

The input and output schema is documented in SKILL.md. This program does not
call banking tools or alter accounts.
"""
import json
import math
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def number(value, field, errors, positive=False):
    try:
        value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        errors.append(field + " must be numeric")
        return None
    if not value.is_finite() or value < 0 or (positive and value <= 0):
        errors.append(field + (" must be positive" if positive else " must be nonnegative"))
        return None
    return value


def rate(apy):
    return Decimal(str(math.expm1(math.log1p(float(apy) / 100) / 365)))


def out(value, places=6):
    return float(value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def selected(candidates, eligibility_keys, value_key, errors, label):
    values = []
    if not isinstance(candidates, list):
        errors.append(label + " must be a list")
        return Decimal("0"), None
    for index, item in enumerate(candidates):
        if not isinstance(item, dict):
            errors.append(f"{label}[{index}] must be an object")
            continue
        if all(item.get(key) is True for key in eligibility_keys):
            amount = number(item.get(value_key), f"{label}[{index}].{value_key}", errors)
            if amount is not None:
                values.append((amount, str(item.get("name", "unnamed"))))
    return max(values, default=(Decimal("0"), None), key=lambda pair: pair[0])


def main(payload):
    if payload.get("daily_balances_complete") is not True:
        return {"status": "insufficient_data", "missing": ["full statement-cycle daily balance history"], "actions": ["Do not credit or report until complete daily balances and a posted interest credit are established."]}

    raw_rows = payload.get("daily_balances")
    if not isinstance(raw_rows, list) or not raw_rows:
        return {"status": "insufficient_data", "missing": ["daily_balances"]}

    errors = []
    actual = number(payload.get("actual_interest_credit"), "actual_interest_credit", errors)
    threshold = number(payload.get("tier_threshold"), "tier_threshold", errors)
    low = number(payload.get("low_tier_apy"), "low_tier_apy", errors)
    high = number(payload.get("high_tier_apy"), "high_tier_apy", errors)
    rows, dates = [], set()
    for index, item in enumerate(raw_rows):
        if not isinstance(item, dict):
            errors.append(f"daily_balances[{index}] must be an object")
            continue
        try:
            day = date.fromisoformat(str(item.get("date")))
            if day in dates:
                errors.append(f"duplicate daily balance date: {day.isoformat()}")
            dates.add(day)
        except (TypeError, ValueError):
            errors.append(f"daily_balances[{index}].date must be YYYY-MM-DD")
            continue
        balance = number(item.get("balance"), f"daily_balances[{index}].balance", errors)
        if balance is not None:
            rows.append((day, balance))
    if errors:
        return {"status": "invalid_input", "errors": errors}
    rows.sort()
    if len(rows) != len(raw_rows):
        return {"status": "invalid_input", "errors": ["each daily balance must have a valid date and balance"]}
    if any((current[0] - previous[0]).days != 1 for previous, current in zip(rows, rows[1:])):
        return {"status": "insufficient_data", "missing": ["every consecutive statement-cycle day"]}

    checking_boost, checking_name = selected(payload.get("checking_candidates", []), ("active", "linked", "qualifying"), "boost_apy", errors, "checking_candidates")
    card_bonus, card_name = selected(payload.get("card_candidates", []), ("active", "applicable"), "bonus_apy", errors, "card_candidates")
    relationship = payload.get("relationship", {})
    if not isinstance(relationship, dict):
        errors.append("relationship must be an object")
        relationship = {}
    relationship_bonus = Decimal("0")
    if relationship.get("eligible") is True:
        relationship_bonus = number(relationship.get("bonus_apy"), "relationship.bonus_apy", errors)
        if relationship_bonus is None:
            relationship_bonus = Decimal("0")
    if errors:
        return {"status": "invalid_input", "errors": errors}

    accrued, day_apys = Decimal("0"), []
    for _, balance in rows:
        base = high if balance >= threshold else low
        apy = base + checking_boost + card_bonus + relationship_bonus
        accrued += (balance + accrued) * rate(apy)
        day_apys.append(apy)
    expected = accrued.quantize(CENT, rounding=ROUND_HALF_UP)
    difference = (expected - actual).quantize(CENT, rounding=ROUND_HALF_UP)
    total_balance = sum((balance for _, balance in rows), Decimal("0"))
    weighted_apy = (sum((balance * apy for (_, balance), apy in zip(rows, day_apys)), Decimal("0")) / total_balance) if total_balance else day_apys[0]

    # Infer a single effective annual APY for reporting only if no applied APY
    # is separately recorded. Binary search matches the posted amount.
    inferred = Decimal("0")
    if actual > 0:
        lower, upper = Decimal("0"), Decimal("1000")
        for _ in range(100):
            mid = (lower + upper) / 2
            trial = Decimal("0")
            for _, balance in rows:
                trial += (balance + trial) * rate(mid)
            if trial < actual:
                lower = mid
            else:
                upper = mid
        inferred = (lower + upper) / 2

    ready = difference > 0
    notes = ["Apply the positive amount_difference as interest_correction, confirm it succeeds, then submit the report."] if ready else ["No positive underpayment was calculated. Do not apply a correction or submit a discrepancy report."]
    if len(set(day_apys)) > 1:
        notes.append("Daily expected APY varied by balance tier; report_expected_apy is balance-weighted. Retain the daily workpaper.")
    return {
        "status": "ready_for_correction" if ready else "no_underpayment",
        "cycle_start": rows[0][0].isoformat(), "cycle_end": rows[-1][0].isoformat(), "days": len(rows),
        "components": {"highest_checking_boost_apy": out(checking_boost), "selected_checking_account": checking_name, "highest_card_bonus_apy": out(card_bonus), "selected_card": card_name, "relationship_bonus_apy": out(relationship_bonus)},
        "expected_interest": out(expected, 2), "actual_interest_credit": out(actual, 2), "amount_difference": out(max(difference, Decimal("0")), 2),
        "report_expected_apy": out(weighted_apy), "actual_apy_inferred": out(inferred), "rate_varies_by_day": len(set(day_apys)) > 1, "notes": notes
    }


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("stdin JSON must be an object")
        print(json.dumps(main(incoming), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"status": "invalid_input", "errors": [str(exc)]}, separators=(",", ":")))
