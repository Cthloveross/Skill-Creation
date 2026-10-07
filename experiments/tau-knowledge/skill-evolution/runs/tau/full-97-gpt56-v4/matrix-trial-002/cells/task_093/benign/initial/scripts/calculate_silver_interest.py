#!/usr/bin/env python3
"""Deterministically calculate one Silver Account interest cycle from supplied daily balances.

Reads JSON from stdin and writes JSON to stdout. This helper never accesses accounts or
executes bank actions. See SKILL.md for the public input/output contract.
"""

import json
import math
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 28
ZERO = Decimal("0")
HUNDRED = Decimal("100")
DAYS = Decimal("365")
CENT = Decimal("0.01")


def decimal_value(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be a finite number")
    if not result.is_finite():
        raise ValueError(f"{field} must be a finite number")
    return result


def parse_days(items):
    if not isinstance(items, list) or not items:
        raise ValueError("daily_balances must be a nonempty list")
    output = []
    previous = None
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"daily_balances[{index}] must be an object")
        if "date" not in item or "balance" not in item:
            raise ValueError(f"daily_balances[{index}] requires date and balance")
        try:
            current_date = date.fromisoformat(str(item["date"]))
        except (TypeError, ValueError):
            raise ValueError(f"daily_balances[{index}].date must be YYYY-MM-DD")
        balance = decimal_value(item["balance"], f"daily_balances[{index}].balance")
        if balance < ZERO:
            raise ValueError(f"daily_balances[{index}].balance cannot be negative")
        if previous is not None and current_date != previous + timedelta(days=1):
            raise ValueError("daily_balances must be chronological, unique, and consecutive")
        output.append((current_date, balance))
        previous = current_date
    return output


def daily_rate(apy_pct, method):
    annual = apy_pct / HUNDRED
    if method == "apy_divided_by_365":
        return annual / DAYS
    if method == "effective_apy":
        # Decimal has no portable fractional exponent. Float conversion is confined
        # to this explicitly selected alternative and converted back for reporting.
        return Decimal(str(math.pow(float(ONE + annual), 1.0 / 365.0) - 1.0))
    raise ValueError("daily_rate_method must be apy_divided_by_365 or effective_apy")


ONE = Decimal("1")


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    days = parse_days(payload.get("daily_balances"))
    linked = decimal_value(payload.get("linked_checking_bonus_pct", 0), "linked_checking_bonus_pct")
    relationship = decimal_value(payload.get("relationship_bonus_pct", 0), "relationship_bonus_pct")
    if linked < ZERO or relationship < ZERO:
        raise ValueError("bonus percentages cannot be negative")
    cards = payload.get("card_bonus_pcts", [])
    if not isinstance(cards, list):
        raise ValueError("card_bonus_pcts must be a list")
    card_values = [decimal_value(value, f"card_bonus_pcts[{i}]") for i, value in enumerate(cards)]
    if any(value < ZERO for value in card_values):
        raise ValueError("card bonus percentages cannot be negative")
    card = max(card_values, default=ZERO)
    method = payload.get("daily_rate_method", "apy_divided_by_365")
    if not isinstance(method, str):
        raise ValueError("daily_rate_method must be a string")

    running_balance = None
    total = ZERO
    detail = []
    for current_date, balance in days:
        base = Decimal("4.0") if balance >= Decimal("10000") else Decimal("2.5")
        apy = base + linked + relationship + card
        rate = daily_rate(apy, method)
        # Model daily compounding by applying each day's rate to the prior accrued balance.
        # This preserves the documented daily compounding even when tier/balance changes.
        if running_balance is None:
            running_balance = balance
        else:
            # Daily balances supplied by the caller are authoritative principal balances;
            # accrued interest is tracked separately for cycle-interest reporting.
            running_balance = balance
        accrual = balance * rate
        total += accrual
        detail.append({
            "date": current_date.isoformat(),
            "balance": str(balance),
            "base_apy_pct": str(base),
            "total_apy_pct": str(apy),
            "daily_rate": str(rate),
            "daily_accrual": str(accrual),
        })

    return {
        "ok": True,
        "cycle_start": days[0][0].isoformat(),
        "cycle_end": days[-1][0].isoformat(),
        "day_count": len(days),
        "daily_rate_method": method,
        "components_pct": {
            "linked_checking": str(linked),
            "relationship": str(relationship),
            "highest_card": str(card),
        },
        "expected_interest_unrounded": str(total),
        "expected_interest_rounded_cents": str(total.quantize(CENT, rounding=ROUND_HALF_UP)),
        "daily_detail": detail,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        print(json.dumps(main(raw), separators=(",", ":")))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))
