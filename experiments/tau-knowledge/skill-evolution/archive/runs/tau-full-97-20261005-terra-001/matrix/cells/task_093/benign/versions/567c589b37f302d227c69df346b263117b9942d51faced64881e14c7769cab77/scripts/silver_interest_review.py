#!/usr/bin/env python3
"""Calculate or identify evidence for a Silver Account interest review.

Read one JSON object from stdin and write one JSON object to stdout.
No network, file, or banking actions are performed.
"""

import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40
ZERO = Decimal("0")
HUNDRED = Decimal("100")
THRESHOLD = Decimal("10000")
BASE_LOW = Decimal("2.5")
BASE_HIGH = Decimal("4.0")
CENT = Decimal("0.01")


def decimal_value(value, field, nonnegative=True):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be a decimal number")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    if nonnegative and result < ZERO:
        raise ValueError(f"{field} must not be negative")
    return result


def parse_date(value, field="date"):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a date string")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"{field} must use YYYY-MM-DD or MM/DD/YYYY")


def money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def number(value, places=10):
    quantizer = Decimal("1").scaleb(-places)
    return format(value.quantize(quantizer, rounding=ROUND_HALF_UP), "f")


def max_bonus(values, field):
    if values is None:
        return ZERO
    if not isinstance(values, list):
        raise ValueError(f"{field} must be a list of percentage values")
    parsed = [decimal_value(item, f"{field}[{idx}]") for idx, item in enumerate(values)]
    return max(parsed) if parsed else ZERO


def daily_rate(annual_pct, method):
    annual_fraction = annual_pct / HUNDRED
    if method == "effective_apy_daily":
        # Decimal supports non-integral powers on supported Python versions;
        # float is avoided for monetary totals where feasible.
        return (Decimal(1) + annual_fraction) ** (Decimal(1) / Decimal(365)) - Decimal(1)
    if method == "nominal_apy_div_365":
        return annual_fraction / Decimal(365)
    raise ValueError("daily_rate_method must be effective_apy_daily or nominal_apy_div_365")


def find_interest_credits(data):
    transactions = data.get("transactions")
    if not isinstance(transactions, list):
        raise ValueError("transactions must be a list")
    candidates = []
    for index, transaction in enumerate(transactions):
        if not isinstance(transaction, dict):
            raise ValueError(f"transactions[{index}] must be an object")
        if transaction.get("type") == "interest_credit" and transaction.get("status") == "posted":
            item = {
                "transaction_id": transaction.get("transaction_id"),
                "date": transaction.get("date"),
                "description": transaction.get("description"),
                "amount": transaction.get("amount"),
                "status": "posted",
                "type": "interest_credit",
            }
            candidates.append(item)
    return {
        "ok": True,
        "operation": "find_interest_credits",
        "posted_interest_credits": candidates,
        "count": len(candidates),
        "warning": (
            "Select the credit that matches the statement period; this filter does not "
            "prove the credit amount or applicable APY."
        ),
    }


def calculate(data):
    balances = data.get("daily_balances")
    if not isinstance(balances, list) or not balances:
        raise ValueError("daily_balances must be a nonempty list with one entry per calendar day")

    checking_bonus = max_bonus(data.get("checking_boosts_pct", []), "checking_boosts_pct")
    card_bonus = max_bonus(data.get("credit_card_bonuses_pct", []), "credit_card_bonuses_pct")
    relationship_bonus = decimal_value(data.get("relationship_bonus_pct", "0"), "relationship_bonus_pct")
    method = data.get("daily_rate_method", "effective_apy_daily")

    parsed = []
    dates_seen = set()
    for index, row in enumerate(balances):
        if not isinstance(row, dict):
            raise ValueError(f"daily_balances[{index}] must be an object")
        day = parse_date(row.get("date"), f"daily_balances[{index}].date")
        if day in dates_seen:
            raise ValueError(f"daily_balances contains duplicate date {day.isoformat()}")
        dates_seen.add(day)
        balance = decimal_value(row.get("balance"), f"daily_balances[{index}].balance")
        parsed.append((day, balance))

    parsed.sort(key=lambda pair: pair[0])
    for previous, current in zip(parsed, parsed[1:]):
        if current[0] != previous[0] + timedelta(days=1):
            raise ValueError(
                "daily_balances must be contiguous; missing day(s) between "
                f"{previous[0].isoformat()} and {current[0].isoformat()}"
            )

    total = ZERO
    daily_results = []
    low_days = 0
    high_days = 0
    for day, balance in parsed:
        if balance >= THRESHOLD:
            base = BASE_HIGH
            tier = "higher"
            high_days += 1
        else:
            base = BASE_LOW
            tier = "lower"
            low_days += 1
        annual_pct = base + checking_bonus + card_bonus + relationship_bonus
        rate = daily_rate(annual_pct, method)
        accrual = balance * rate
        total += accrual
        daily_results.append({
            "date": day.isoformat(),
            "balance": money(balance),
            "tier": tier,
            "base_apy_pct": number(base, 3),
            "total_apy_pct": number(annual_pct, 3),
            "daily_rate": number(rate, 12),
            "unrounded_accrual": number(accrual, 12),
        })

    expected_rounded = total.quantize(CENT, rounding=ROUND_HALF_UP)
    result = {
        "ok": True,
        "operation": "calculate",
        "period": {"start": parsed[0][0].isoformat(), "end": parsed[-1][0].isoformat(), "days": len(parsed)},
        "selected_components_pct": {
            "highest_checking_boost": number(checking_bonus, 3),
            "highest_credit_card_bonus": number(card_bonus, 3),
            "relationship_bonus": number(relationship_bonus, 3),
            "lower_tier_total_apy": number(BASE_LOW + checking_bonus + card_bonus + relationship_bonus, 3),
            "higher_tier_total_apy": number(BASE_HIGH + checking_bonus + card_bonus + relationship_bonus, 3),
        },
        "tier_days": {"lower": low_days, "higher": high_days},
        "daily_rate_method": method,
        "expected_interest_unrounded": number(total, 12),
        "expected_interest_rounded": money(expected_rounded),
        "daily_accruals": daily_results,
        "warnings": [
            "Bonus inputs must contain only confirmed, eligible bonuses.",
            "Checking and card lists are reduced to their highest values; they are not stacked.",
            "The rounded result is a calculation aid and does not alone establish a bank error."
        ],
    }

    if "actual_interest_credit" in data and data.get("actual_interest_credit") is not None:
        actual = decimal_value(data["actual_interest_credit"], "actual_interest_credit")
        difference = expected_rounded - actual
        result["actual_interest_credit"] = money(actual)
        result["expected_minus_actual"] = money(difference)
        result["positive_shortfall"] = money(difference) if difference > ZERO else "0.00"
        if difference > ZERO:
            result["comparison"] = "expected interest exceeds supplied posted credit"
        elif difference < ZERO:
            result["comparison"] = "supplied posted credit meets or exceeds calculated interest"
        else:
            result["comparison"] = "supplied posted credit equals calculated interest after rounding"
    return result


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        operation = data.get("operation")
        if operation == "find_interest_credits":
            output = find_interest_credits(data)
        elif operation == "calculate":
            output = calculate(data)
        else:
            raise ValueError("operation must be find_interest_credits or calculate")
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        output = {"ok": False, "error": str(exc)}
    print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
