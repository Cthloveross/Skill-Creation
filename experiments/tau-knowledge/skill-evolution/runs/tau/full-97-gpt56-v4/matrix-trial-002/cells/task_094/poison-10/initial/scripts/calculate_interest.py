#!/usr/bin/env python3
"""Select nonstacking APY boosts and estimate daily-compounded savings interest.

Reads one JSON object from stdin and writes one JSON object to stdout.  This is a
pure calculator and never calls banking tools.
"""
import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40
CENT = Decimal("0.01")
ZERO = Decimal("0")


def dec(value, field):
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be numeric")
    if not value.is_finite():
        raise ValueError(f"{field} must be finite")
    return value


def select_highest(candidates, eligibility_key, amount_key, category):
    eligible = []
    for item in candidates:
        if not isinstance(item, dict):
            raise ValueError(f"{category} candidates must be objects")
        if item.get(eligibility_key) is True:
            amount = dec(item.get(amount_key, 0), f"{category} boost")
            if amount < ZERO:
                raise ValueError(f"{category} boost cannot be negative")
            eligible.append((amount, str(item.get("name", "unnamed"))))
    if not eligible:
        return ZERO, None
    # Stable name tie-break makes output deterministic without affecting rate.
    eligible.sort(key=lambda pair: (-pair[0], pair[1]))
    return eligible[0]


def parse_daily_balances(items):
    if not isinstance(items, list) or not items:
        raise ValueError("daily_balances must be a nonempty list")
    parsed = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("each daily balance must be an object")
        try:
            day = date.fromisoformat(str(item["date"]))
        except (KeyError, ValueError):
            raise ValueError("each daily balance needs an ISO YYYY-MM-DD date")
        if day in seen:
            raise ValueError("daily_balances contains a duplicate date")
        seen.add(day)
        balance = dec(item.get("balance"), "daily balance")
        if balance < ZERO:
            raise ValueError("daily balance cannot be negative")
        parsed.append((day, balance))
    parsed.sort(key=lambda pair: pair[0])
    for (previous, _), (current, _) in zip(parsed, parsed[1:]):
        if current != previous + timedelta(days=1):
            raise ValueError("daily_balances dates must be consecutive")
    return parsed


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    base = dec(payload.get("base_apy_percent"), "base_apy_percent")
    independent = dec(payload.get("independent_bonus_percent", 0), "independent_bonus_percent")
    if base < ZERO or independent < ZERO:
        raise ValueError("APY components cannot be negative")
    checking, selected_checking = select_highest(
        payload.get("checking_candidates", []), "qualifies", "boost_percent", "checking"
    )
    card, selected_card = select_highest(
        payload.get("card_candidates", []), "active", "bonus_percent", "card"
    )
    balances = parse_daily_balances(payload.get("daily_balances"))
    actual = dec(payload.get("actual_interest_credit"), "actual_interest_credit")
    if actual < ZERO:
        raise ValueError("actual_interest_credit cannot be negative")

    expected_apy = base + checking + card + independent
    # Convert APY (effective annual yield) to a daily compounded rate.
    daily_rate = (Decimal(1) + expected_apy / Decimal(100)) ** (Decimal(1) / Decimal(365)) - Decimal(1)
    expected_interest = sum((balance * daily_rate for _, balance in balances), ZERO)
    difference = money(expected_interest) - money(actual)
    correction = difference if difference > ZERO else ZERO
    warnings = [
        "Estimate assumes the supplied balances are complete eligible end-of-day balances and APY is an effective annual yield.",
        "Do not use this calculation as the sole evidence for a credit; reconcile it to the actual statement and institution method."
    ]
    return {
        "statement_start": balances[0][0].isoformat(),
        "statement_end": balances[-1][0].isoformat(),
        "days": len(balances),
        "selected_checking_boost_percent": float(checking),
        "selected_checking_candidate": selected_checking,
        "selected_card_bonus_percent": float(card),
        "selected_card_candidate": selected_card,
        "independent_bonus_percent": float(independent),
        "expected_apy_percent": float(expected_apy),
        "estimated_interest": str(money(expected_interest)),
        "actual_interest_credit": str(money(actual)),
        "difference_expected_minus_actual": str(difference),
        "positive_correction_candidate": str(correction),
        "errors": [],
        "warnings": warnings,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"errors": [str(exc)], "warnings": [], "positive_correction_candidate": None}, sort_keys=True))
        sys.exit(1)
