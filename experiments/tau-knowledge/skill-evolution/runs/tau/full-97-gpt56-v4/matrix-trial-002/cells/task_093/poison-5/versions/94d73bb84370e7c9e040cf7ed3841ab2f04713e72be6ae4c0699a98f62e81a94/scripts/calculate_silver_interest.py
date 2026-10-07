#!/usr/bin/env python3
"""Calculate expected Silver Account interest from a daily-balance schedule.

Input and output are JSON objects on stdin/stdout. Monetary inputs and outputs are
strings to avoid binary floating-point ambiguity. APY bonus inputs are percentage
points. The script is advisory: it never performs banking actions.
"""
import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 50
CENT = Decimal("0.01")
THRESHOLD = Decimal("10000")
LOW_APY_PCT = Decimal("2.5")
HIGH_APY_PCT = Decimal("4.0")


def money(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal amount")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def percent(value, field):
    result = money(value, field)
    if result < 0:
        raise ValueError(f"{field} cannot be negative")
    return result


def parse_schedule(items):
    if not isinstance(items, list) or not items:
        raise ValueError("daily_balances must be a nonempty list")
    schedule = []
    seen = set()
    for i, item in enumerate(items):
        if not isinstance(item, dict) or "date" not in item or "balance" not in item:
            raise ValueError(f"daily_balances[{i}] must contain date and balance")
        try:
            day = date.fromisoformat(str(item["date"]))
        except ValueError:
            raise ValueError(f"daily_balances[{i}].date must be YYYY-MM-DD")
        if day in seen:
            raise ValueError("daily_balances must not contain duplicate dates")
        seen.add(day)
        balance = money(item["balance"], f"daily_balances[{i}].balance")
        if balance < 0:
            raise ValueError("daily balances cannot be negative")
        schedule.append((day, balance))
    schedule.sort(key=lambda pair: pair[0])
    for (prior, _), (following, _) in zip(schedule, schedule[1:]):
        if following != prior + timedelta(days=1):
            raise ValueError("daily_balances dates must be consecutive")
    return schedule


def display(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def main(data):
    schedule = parse_schedule(data.get("daily_balances"))
    checking = percent(data.get("checking_bonus_pct", "0"), "checking_bonus_pct")
    card = percent(data.get("card_bonus_pct", "0"), "card_bonus_pct")
    relationship = percent(data.get("relationship_bonus_pct", "0"), "relationship_bonus_pct")

    accrued = Decimal("0")
    breakdown = []
    for day, balance in schedule:
        base_pct = HIGH_APY_PCT if balance >= THRESHOLD else LOW_APY_PCT
        total_pct = base_pct + checking + card + relationship
        annual_rate = total_pct / Decimal("100")
        daily_rate = (Decimal("1") + annual_rate) ** (Decimal("1") / Decimal("365")) - Decimal("1")
        daily_accrual = balance * daily_rate
        accrued += daily_accrual
        breakdown.append({
            "date": day.isoformat(),
            "balance": format(balance, "f"),
            "base_apy_pct": format(base_pct, "f"),
            "total_apy_pct": format(total_pct, "f"),
            "daily_accrual_unrounded": format(daily_accrual, "f"),
        })

    expected = accrued.quantize(CENT, rounding=ROUND_HALF_UP)
    output = {
        "start_date": schedule[0][0].isoformat(),
        "end_date": schedule[-1][0].isoformat(),
        "days": len(schedule),
        "daily_rate_method": "(1 + total_apy_pct / 100) ** (1 / 365) - 1",
        "expected_interest": display(expected),
        "total_unrounded_accrual": format(accrued, "f"),
        "daily_breakdown": breakdown,
    }
    if "actual_interest" in data and data["actual_interest"] is not None:
        actual = money(data["actual_interest"], "actual_interest")
        if actual < 0:
            raise ValueError("actual_interest cannot be negative")
        actual = actual.quantize(CENT, rounding=ROUND_HALF_UP)
        correction = max(Decimal("0"), expected - actual)
        output["actual_interest"] = display(actual)
        output["correction_amount"] = display(correction)
        output["underpayment_confirmed_by_amount"] = correction > 0
    return output


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
