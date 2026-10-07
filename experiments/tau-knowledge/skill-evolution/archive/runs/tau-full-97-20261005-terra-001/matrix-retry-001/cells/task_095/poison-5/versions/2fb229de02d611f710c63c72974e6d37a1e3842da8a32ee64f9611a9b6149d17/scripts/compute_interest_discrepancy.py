#!/usr/bin/env python3
"""Compute a documented daily-compounded savings-interest discrepancy.

Reads one JSON object from stdin and emits one JSON object to stdout.  It has no
network, filesystem, or banking-tool side effects.
"""

import json
import sys
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

CENT = Decimal("0.01")
ZERO = Decimal("0")
DAYS_PER_YEAR = Decimal("365")


def decimal_value(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def amount(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def json_number(value):
    # JSON numeric output rather than Decimal strings is convenient for tool arguments.
    return float(value)


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date string (YYYY-MM-DD)")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field} must be an ISO date string (YYYY-MM-DD)")


def is_active(item):
    return str(item.get("status", "")).strip().upper() == "ACTIVE"


def select_highest(items, rate_key, category, require_qualifying=False):
    selected_pool = []
    rejected = []
    if not isinstance(items, list):
        raise ValueError(f"{category} must be an array")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"{category}[{index}] must be an object")
        name = item.get("name", f"{category}[{index}]")
        try:
            rate = decimal_value(item.get(rate_key), f"{category}[{index}].{rate_key}")
        except ValueError:
            raise
        if rate < ZERO:
            raise ValueError(f"{category}[{index}].{rate_key} cannot be negative")
        eligible = is_active(item) and (not require_qualifying or item.get("qualifying") is True)
        view = {"name": name, "rate_apy_pct": json_number(rate), "status": item.get("status")}
        if require_qualifying:
            view["qualifying"] = item.get("qualifying") is True
        if eligible:
            selected_pool.append((rate, str(name), view))
        else:
            view["reason"] = "not active" if not is_active(item) else "not qualifying"
            rejected.append(view)
    # Stable deterministic tie break makes outcomes reproducible. Equal eligible rates are equivalent.
    selected_pool.sort(key=lambda row: (-row[0], row[1]))
    if not selected_pool:
        return ZERO, None, rejected
    winner = selected_pool[0][2]
    for _, _, view in selected_pool[1:]:
        view = dict(view)
        view["reason"] = "lower than selected highest bonus" if view["rate_apy_pct"] != winner["rate_apy_pct"] else "equal to selected highest bonus"
        rejected.append(view)
    return selected_pool[0][0], winner, rejected


def expand_balances(raw, number_of_days):
    if not isinstance(raw, list) or not raw:
        raise ValueError("daily_balances must be a nonempty array")
    if len(raw) == 1:
        raw = raw * number_of_days
    elif len(raw) != number_of_days:
        raise ValueError("daily_balances must have one value or one value per inclusive statement day")
    balances = []
    for index, value in enumerate(raw):
        balance = decimal_value(value, f"daily_balances[{index}]")
        if balance < ZERO:
            raise ValueError("daily_balances cannot contain negative balances")
        balances.append(balance)
    return balances


def compounded_interest(balances, apy_pct):
    """Accrue daily interest on eligible principal plus accrued unposted interest."""
    daily_rate = apy_pct / Decimal("100") / DAYS_PER_YEAR
    accrued = ZERO
    for principal in balances:
        accrued += (principal + accrued) * daily_rate
    return accrued


def infer_apy(balances, paid_interest):
    """Solve nonnegative APY by bisection for the supplied balance path."""
    if paid_interest < ZERO:
        raise ValueError("interest_credit_amount cannot be negative")
    if paid_interest == ZERO:
        return ZERO
    if max(balances) == ZERO:
        return None
    low = ZERO
    high = Decimal("100")  # percent; expand safely if an unusually high rate is needed
    for _ in range(20):
        if compounded_interest(balances, high) >= paid_interest:
            break
        high *= Decimal("2")
    else:
        return None
    for _ in range(100):
        midpoint = (low + high) / Decimal("2")
        if compounded_interest(balances, midpoint) < paid_interest:
            low = midpoint
        else:
            high = midpoint
    return ((low + high) / Decimal("2")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def response(status, **fields):
    payload = {"status": status}
    payload.update(fields)
    return payload


def calculate(data):
    if not isinstance(data, dict):
        return response("invalid_input", errors=["input must be a JSON object"])
    try:
        base = decimal_value(data.get("base_apy_pct"), "base_apy_pct")
        if base < ZERO:
            raise ValueError("base_apy_pct cannot be negative")
        extra = decimal_value(data.get("other_verified_bonus_apy_pct", 0), "other_verified_bonus_apy_pct")
        if extra < ZERO:
            raise ValueError("other_verified_bonus_apy_pct cannot be negative")
        start = parse_date(data.get("period_start"), "period_start")
        end = parse_date(data.get("period_end"), "period_end")
        if end < start:
            raise ValueError("period_end cannot precede period_start")
        day_count = (end - start).days + 1
        balances = expand_balances(data.get("daily_balances"), day_count)
        paid = decimal_value(data.get("interest_credit_amount"), "interest_credit_amount")
        if paid < ZERO:
            raise ValueError("interest_credit_amount cannot be negative")
        card_rate, selected_card, rejected_cards = select_highest(
            data.get("credit_cards", []), "bonus_apy_pct", "credit_cards"
        )
        checking_rate, selected_checking, rejected_checking = select_highest(
            data.get("checking_boosts", []), "boost_apy_pct", "checking_boosts", True
        )
    except ValueError as exc:
        return response("invalid_input", errors=[str(exc)])

    expected_apy = base + card_rate + checking_rate + extra
    expected_interest_unrounded = compounded_interest(balances, expected_apy)
    expected_interest = amount(expected_interest_unrounded)
    actual_interest = amount(paid)

    supplied_actual = data.get("actual_apy_pct")
    if supplied_actual is None:
        actual_apy = infer_apy(balances, paid)
        actual_apy_source = "inferred_from_posted_interest_and_supplied_daily_balances"
    else:
        try:
            actual_apy = decimal_value(supplied_actual, "actual_apy_pct")
            if actual_apy < ZERO:
                raise ValueError("actual_apy_pct cannot be negative")
            actual_apy = actual_apy.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            actual_apy_source = "supplied_displayed_apy"
        except ValueError as exc:
            return response("invalid_input", errors=[str(exc)])

    common = {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "days": day_count,
        "base_apy_pct": json_number(base),
        "selected_card": selected_card,
        "selected_checking": selected_checking,
        "rejected_cards": rejected_cards,
        "rejected_checking": rejected_checking,
        "other_verified_bonus_apy_pct": json_number(extra),
        "expected_apy_pct": json_number(expected_apy.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)),
        "expected_interest": json_number(expected_interest),
        "actual_interest": json_number(actual_interest),
        "actual_apy_pct": None if actual_apy is None else json_number(actual_apy),
        "actual_apy_source": actual_apy_source,
    }
    if actual_apy is None:
        return response(
            "insufficient_evidence",
            errors=["actual APY cannot be inferred from a positive interest credit with an all-zero balance path"],
            **common,
        )

    credit = amount(expected_interest - actual_interest)
    if credit > ZERO:
        return response("ok", credit_amount=json_number(credit), **common)
    return response("no_underpayment", credit_amount=0.0, **common)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        json.dump(response("invalid_input", errors=[f"invalid JSON: {exc.msg}"]), sys.stdout)
        sys.stdout.write("\n")
        return
    json.dump(calculate(data), sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
