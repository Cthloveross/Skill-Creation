#!/usr/bin/env python3
"""Calculate a reviewable savings-interest discrepancy from daily balances.
Reads one JSON object from stdin and writes one JSON result to stdout.
"""
import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40
CENT = Decimal("0.01")
DAYS_PER_YEAR = Decimal("365")


def money(value):
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def pct(value):
    return Decimal(str(value))


def main(payload):
    errors = []
    account_id = payload.get("account_id")
    if not isinstance(account_id, str) or not account_id.strip():
        errors.append("account_id must be a nonempty string")

    try:
        expected_apy = pct(payload.get("expected_apy_percent"))
        if expected_apy < 0:
            errors.append("expected_apy_percent must be nonnegative")
    except (InvalidOperation, TypeError, ValueError):
        expected_apy = Decimal(0)
        errors.append("expected_apy_percent must be numeric")

    try:
        actual_credit = money(payload.get("actual_credit_amount"))
        if actual_credit < 0:
            errors.append("actual_credit_amount must be nonnegative")
    except (InvalidOperation, TypeError, ValueError):
        actual_credit = Decimal(0)
        errors.append("actual_credit_amount must be numeric")

    rows = payload.get("daily_balances")
    parsed = []
    if not isinstance(rows, list) or not rows:
        errors.append("daily_balances must be a nonempty list")
    else:
        seen = set()
        for index, row in enumerate(rows):
            try:
                if not isinstance(row, dict):
                    raise ValueError("not an object")
                day = date.fromisoformat(row["date"])
                balance = Decimal(str(row["balance"]))
                if balance < 0:
                    raise ValueError("negative balance")
                if day in seen:
                    raise ValueError("duplicate date")
                seen.add(day)
                parsed.append((day, balance))
            except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
                errors.append("invalid daily_balances entry at index %d: %s" % (index, exc))
        if parsed:
            parsed.sort(key=lambda item: item[0])
            for prior, current in zip(parsed, parsed[1:]):
                if current[0] != prior[0] + timedelta(days=1):
                    errors.append("daily_balances must cover consecutive calendar days")
                    break

    supplied_actual = payload.get("actual_apy_percent")
    actual_apy = None
    actual_apy_source = "inferred"
    if supplied_actual is not None:
        try:
            actual_apy = pct(supplied_actual)
            if actual_apy < 0:
                errors.append("actual_apy_percent must be nonnegative")
        except (InvalidOperation, TypeError, ValueError):
            errors.append("actual_apy_percent must be numeric or null")

    expected_interest = Decimal(0)
    weighted_balance = Decimal(0)
    if not errors:
        # APY is an effective annual yield. Convert it to a daily effective rate,
        # then sum daily accruals over the supplied statement period.
        expected_daily_rate = (Decimal(1) + expected_apy / Decimal(100)) ** (Decimal(1) / DAYS_PER_YEAR) - Decimal(1)
        weighted_balance = sum((balance for _, balance in parsed), Decimal(0))
        expected_interest = money(sum((balance * expected_daily_rate for _, balance in parsed), Decimal(0)))
        if actual_apy is None:
            if weighted_balance == 0:
                errors.append("cannot infer actual APY when all daily balances are zero")
            else:
                inferred_daily_rate = Decimal(actual_credit) / weighted_balance
                actual_apy = ((Decimal(1) + inferred_daily_rate) ** DAYS_PER_YEAR - Decimal(1)) * Decimal(100)
        else:
            actual_apy_source = "provided"

    correction = money(max(Decimal(0), expected_interest - actual_credit))
    result = {
        "account_id": account_id,
        "statement_start": parsed[0][0].isoformat() if parsed else None,
        "statement_end": parsed[-1][0].isoformat() if parsed else None,
        "day_count": len(parsed),
        "expected_apy_percent": str(expected_apy),
        "actual_apy_percent": str(actual_apy.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)) if actual_apy is not None else None,
        "actual_apy_source": actual_apy_source,
        "expected_interest_amount": format(expected_interest, ".2f"),
        "posted_interest_amount": format(actual_credit, ".2f"),
        "correction_amount": format(correction, ".2f"),
        "eligible_for_interest_correction": (not errors and correction > 0),
        "errors": errors,
        "notes": [
            "This calculation needs a verified posted interest_credit and matching complete statement-period balances.",
            "Confirm applicable APY components and tier changes independently before using the result in a banking action."
        ]
    }
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON input must be an object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"eligible_for_interest_correction": False, "errors": [str(exc)]}, sort_keys=True))
        sys.exit(1)
