#!/usr/bin/env python3
"""Compute a policy-based expected APY and, with complete data, an interest projection.

Input and output are JSON objects on stdin/stdout. This script never calls banking tools.
"""
import json
import math
import sys
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

CENT = Decimal("0.01")


def number(value, name, errors):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f"{name} must be numeric")
        return None
    if not result.is_finite():
        errors.append(f"{name} must be finite")
        return None
    return result


def is_active(item):
    return str(item.get("status", "")).strip().upper() == "ACTIVE"


def selected(items, amount_field, eligibility_field, category, errors):
    if not isinstance(items, list):
        errors.append(f"{category} must be a list")
        return Decimal("0"), []
    eligible = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{category}[{index}] must be an object")
            continue
        if is_active(item) and item.get(eligibility_field) is True:
            amount = number(item.get(amount_field), f"{category}[{index}].{amount_field}", errors)
            if amount is not None:
                if amount < 0:
                    errors.append(f"{category}[{index}].{amount_field} cannot be negative")
                else:
                    eligible.append((amount, str(item.get("type", "unlabeled"))))
    if not eligible:
        return Decimal("0"), []
    maximum = max(pair[0] for pair in eligible)
    return maximum, [label for amount, label in eligible if amount == maximum]


def parse_history(history, errors):
    if not isinstance(history, list) or not history:
        errors.append("balance_history must be a nonempty list for an interest projection")
        return []
    parsed = []
    seen = set()
    for index, row in enumerate(history):
        if not isinstance(row, dict):
            errors.append(f"balance_history[{index}] must be an object")
            continue
        try:
            day = date.fromisoformat(str(row.get("date")))
        except (ValueError, TypeError):
            errors.append(f"balance_history[{index}].date must be YYYY-MM-DD")
            continue
        balance = number(row.get("balance"), f"balance_history[{index}].balance", errors)
        if balance is not None and balance < 0:
            errors.append(f"balance_history[{index}].balance cannot be negative")
        if day in seen:
            errors.append("balance_history dates must be unique")
        seen.add(day)
        if balance is not None and balance >= 0:
            parsed.append((day, balance))
    parsed.sort(key=lambda x: x[0])
    for prior, current in zip(parsed, parsed[1:]):
        if current[0] != prior[0] + timedelta(days=1):
            errors.append("balance_history dates must be consecutive calendar days")
            break
    return parsed


def main(payload):
    errors = []
    warnings = []
    base = number(payload.get("base_apy"), "base_apy", errors)
    if base is not None and base < 0:
        errors.append("base_apy cannot be negative")
    base_eligible = payload.get("base_rate_eligible")
    if not isinstance(base_eligible, bool):
        errors.append("base_rate_eligible must be true or false")
    card_bonus, selected_cards = selected(payload.get("cards", []), "apy_bonus", "eligible", "cards", errors)
    checking_bonus, selected_checking = selected(payload.get("checking_accounts", []), "apy_boost", "qualifies_for_savings", "checking_accounts", errors)
    expected = None
    if base is not None and base >= 0 and isinstance(base_eligible, bool):
        if base_eligible:
            expected = base + card_bonus + checking_bonus
        else:
            warnings.append("Base-rate eligibility is false; no expected APY or correction is calculated.")

    supplied_projection_fields = [key in payload for key in ("balance_history", "reported_interest", "actual_apy")]
    projection = None
    ready = False
    if any(supplied_projection_fields):
        if not all(supplied_projection_fields):
            errors.append("balance_history, reported_interest, and actual_apy must be supplied together")
        elif expected is not None:
            history = parse_history(payload["balance_history"], errors)
            reported = number(payload["reported_interest"], "reported_interest", errors)
            actual = number(payload["actual_apy"], "actual_apy", errors)
            if actual is not None and actual < 0:
                errors.append("actual_apy cannot be negative")
            if not errors and history and reported is not None and actual is not None:
                annual = float(expected / Decimal("100"))
                daily_rate = Decimal(str(math.pow(1.0 + annual, 1.0 / 365.0) - 1.0))
                accrued = Decimal("0")
                for _, balance in history:
                    accrued += (balance + accrued) * daily_rate
                expected_interest = accrued.quantize(CENT, rounding=ROUND_HALF_UP)
                difference = (expected_interest - reported).quantize(CENT, rounding=ROUND_HALF_UP)
                projection = {
                    "days": len(history),
                    "expected_interest": float(expected_interest),
                    "reported_interest": float(reported.quantize(CENT, rounding=ROUND_HALF_UP)),
                    "amount_difference": float(difference),
                    "actual_apy": float(actual),
                    "assumption": "Daily balances are principal before uncredited accrued interest; accrued interest is compounded daily."
                }
                ready = difference > 0 and actual != expected

    result = {
        "expected_apy": float(expected) if expected is not None else None,
        "components": {
            "base_apy": float(base) if base is not None and base_eligible is True else None,
            "highest_card_bonus": float(card_bonus),
            "selected_card_types": selected_cards,
            "highest_checking_boost": float(checking_bonus),
            "selected_checking_types": selected_checking
        },
        "projection": projection,
        "ready_for_credit_and_report": ready,
        "errors": errors,
        "warnings": warnings
    }
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"expected_apy": None, "ready_for_credit_and_report": False, "errors": [str(exc)]}))
        sys.exit(1)
