#!/usr/bin/env python3
"""Select non-stacking APY bonuses and calculate a supported daily-compound period.

Reads one JSON object from stdin and writes one JSON object to stdout. The program
never accesses bank systems and never rounds an adjustment upward: correction_amount
is the positive, cent-rounded difference between expected credited interest and the
posted interest supplied by the caller.
"""

import json
import math
import sys
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation, getcontext

getcontext().prec = 34
CENT = Decimal("0.01")


def fail(message):
    return {"ok": False, "error": message}


def dec(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be numeric")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def candidate_list(raw, amount_key, label):
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{label} must be an array")
    result = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"{label}[{index}] must be an object")
        if not isinstance(item.get("name"), str) or not item["name"].strip():
            raise ValueError(f"{label}[{index}].name is required")
        if not isinstance(item.get("active"), bool) or not isinstance(item.get("qualifies"), bool):
            raise ValueError(f"{label}[{index}] requires boolean active and qualifies")
        amount = dec(item.get(amount_key), f"{label}[{index}].{amount_key}")
        if amount < 0:
            raise ValueError(f"{label}[{index}].{amount_key} cannot be negative")
        result.append({
            "name": item["name"].strip(),
            "amount": amount,
            "eligible": item["active"] and item["qualifies"],
        })
    return result


def choose(candidates):
    eligible = [item for item in candidates if item["eligible"]]
    if not eligible:
        return {"name": None, "amount": Decimal("0")}
    # Stable ordering makes equal-rate selection deterministic while retaining input order.
    return max(eligible, key=lambda item: item["amount"])


def parse_daily_balances(raw):
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        raise ValueError("daily_balances must be a nonempty array when supplied")
    parsed = []
    seen = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"daily_balances[{index}] must be an object")
        try:
            day = date.fromisoformat(str(item.get("date")))
        except (TypeError, ValueError):
            raise ValueError(f"daily_balances[{index}].date must be ISO YYYY-MM-DD")
        if day in seen:
            raise ValueError("daily_balances must not contain duplicate dates")
        seen.add(day)
        balance = dec(item.get("balance"), f"daily_balances[{index}].balance")
        if balance < 0:
            raise ValueError("daily balances cannot be negative")
        parsed.append((day, balance))
    parsed.sort(key=lambda entry: entry[0])
    for previous, current in zip(parsed, parsed[1:]):
        if current[0] != previous[0] + timedelta(days=1):
            raise ValueError("daily_balances must contain every calendar day in the period")
    return parsed


def daily_rate_from_apy(apy_percent, days_per_year):
    # APY-to-daily conversion is valid only when the supplied disclosure uses this
    # effective-APY convention. The caller is responsible for confirming that fact.
    annual = float(apy_percent / Decimal("100"))
    return Decimal(str(math.expm1(math.log1p(annual) / days_per_year)))


def compound_interest(balances, daily_rate):
    accrued = Decimal("0")
    for _, balance in balances:
        accrued = (accrued + balance) * (Decimal("1") + daily_rate) - balance
    return accrued


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def implied_apy(balances, posted_interest, days_per_year):
    """Solve for effective annual APY producing the unrounded posted amount."""
    target = float(posted_interest)
    if target < 0:
        return None
    low, high = 0.0, 100.0  # annual decimal rates, then expanded if necessary
    def earned(rate):
        daily = Decimal(str(math.expm1(math.log1p(rate) / days_per_year)))
        return float(compound_interest(balances, daily))
    while earned(high) < target and high < 1000000.0:
        high *= 2.0
    if earned(high) < target:
        return None
    for _ in range(100):
        midpoint = (low + high) / 2.0
        if earned(midpoint) < target:
            low = midpoint
        else:
            high = midpoint
    return Decimal(str((low + high) / 2.0 * 100))


def main(payload):
    if not isinstance(payload, dict):
        return fail("input must be a JSON object")
    try:
        base = dec(payload.get("base_apy"), "base_apy")
        if base < 0:
            raise ValueError("base_apy cannot be negative")
        checking = candidate_list(payload.get("checking_candidates", []), "boost_apy", "checking_candidates")
        cards = candidate_list(payload.get("card_candidates", []), "bonus_apy", "card_candidates")
        selected_checking = choose(checking)
        selected_card = choose(cards)
        expected_apy = base + selected_checking["amount"] + selected_card["amount"]
        output = {
            "ok": True,
            "base_apy": str(base),
            "selected_checking": {
                "name": selected_checking["name"],
                "boost_apy": str(selected_checking["amount"]),
            },
            "selected_card": {
                "name": selected_card["name"],
                "bonus_apy": str(selected_card["amount"]),
            },
            "expected_apy": str(expected_apy),
            "calculation_ready": False,
            "calculation": None,
        }
        balances = parse_daily_balances(payload.get("daily_balances"))
        if balances is None:
            output["reason"] = "Daily balances and a disclosed day-count convention are required for an exact interest calculation."
            return output
        days_per_year = payload.get("days_per_year")
        if not isinstance(days_per_year, int) or isinstance(days_per_year, bool) or days_per_year <= 0:
            raise ValueError("days_per_year must be a positive integer when daily_balances is supplied")
        daily_rate = daily_rate_from_apy(expected_apy, days_per_year)
        expected_raw = compound_interest(balances, daily_rate)
        calculation = {
            "period_start": balances[0][0].isoformat(),
            "period_end": balances[-1][0].isoformat(),
            "days": len(balances),
            "daily_rate": str(daily_rate),
            "expected_interest_unrounded": str(expected_raw),
            "expected_interest_rounded": str(money(expected_raw)),
            "rate_convention": "effective APY converted to a daily rate using supplied days_per_year",
        }
        if "actual_interest_credit" in payload and payload["actual_interest_credit"] is not None:
            actual = dec(payload["actual_interest_credit"], "actual_interest_credit")
            if actual < 0:
                raise ValueError("actual_interest_credit cannot be negative")
            correction = money(expected_raw) - money(actual)
            implied = implied_apy(balances, actual, days_per_year)
            calculation.update({
                "actual_interest_credit": str(money(actual)),
                "difference_before_rounding": str(expected_raw - actual),
                "correction_amount": str(correction if correction > 0 else Decimal("0.00")),
                "underpayment_established": correction > 0,
                "implied_actual_apy": None if implied is None else str(implied.quantize(Decimal("0.000001"))),
            })
        else:
            calculation["underpayment_established"] = False
            calculation["reason"] = "A posted actual_interest_credit is required to determine a correction."
        output["calculation_ready"] = True
        output["calculation"] = calculation
        return output
    except ValueError as error:
        return fail(str(error))
    except (OverflowError, ArithmeticError) as error:
        return fail(f"calculation failed: {error}")


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
    except json.JSONDecodeError as error:
        json.dump(fail(f"invalid JSON input: {error.msg}"), sys.stdout)
        sys.stdout.write("\n")
        sys.exit(0)
    json.dump(main(incoming), sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
