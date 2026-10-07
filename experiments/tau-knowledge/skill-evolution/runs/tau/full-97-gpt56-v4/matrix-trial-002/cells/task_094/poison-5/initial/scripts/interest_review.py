#!/usr/bin/env python3
"""Select non-stacking APY components and validate evidence for an interest correction.

Reads a JSON object on stdin and writes one JSON object on stdout. All rates are
percentage points (for example, 5.5 means 5.5%). No bank actions are performed.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40
ZERO = Decimal("0")
CENT = Decimal("0.01")


def decimal_value(value, field, errors, nonnegative=True):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f"{field} must be a number")
        return None
    if not result.is_finite():
        errors.append(f"{field} must be finite")
        return None
    if nonnegative and result < ZERO:
        errors.append(f"{field} must not be negative")
        return None
    return result


def candidate_bonus(items, group, errors):
    if items is None:
        return ZERO, None
    if not isinstance(items, list):
        errors.append(f"{group}_candidates must be an array")
        return ZERO, None
    eligible = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{group}_candidates[{index}] must be an object")
            continue
        active = item.get("active")
        qualifies = item.get("qualifies")
        if not isinstance(active, bool) or not isinstance(qualifies, bool):
            errors.append(f"{group}_candidates[{index}] requires boolean active and qualifies")
            continue
        bonus = decimal_value(item.get("bonus_apy"), f"{group}_candidates[{index}].bonus_apy", errors)
        if bonus is not None and active and qualifies:
            eligible.append((bonus, index, item))
    if not eligible:
        return ZERO, None
    bonus, index, item = max(eligible, key=lambda row: row[0])
    selected = {"index": index, "bonus_apy": float(bonus)}
    for key in ("account_id", "label", "card_type"):
        if key in item:
            selected[key] = item[key]
    return bonus, selected


def relationship_total(items, errors):
    if items is None:
        return ZERO
    if not isinstance(items, list):
        errors.append("relationship_bonuses must be an array")
        return ZERO
    total = ZERO
    for index, item in enumerate(items):
        value = item.get("bonus_apy") if isinstance(item, dict) else item
        bonus = decimal_value(value, f"relationship_bonuses[{index}]", errors)
        if bonus is not None:
            total += bonus
    return total


def main(data):
    if not isinstance(data, dict):
        return {"errors": ["input must be a JSON object"], "action_ready": False}

    errors = []
    base = None
    if "base_apy" not in data:
        errors.append("base_apy is required")
    else:
        base = decimal_value(data.get("base_apy"), "base_apy", errors)

    checking, selected_checking = candidate_bonus(data.get("checking_candidates"), "checking", errors)
    card, selected_card = candidate_bonus(data.get("card_candidates"), "card", errors)
    relationship = relationship_total(data.get("relationship_bonuses"), errors)

    output = {
        "selected_checking_bonus": float(checking),
        "selected_card_bonus": float(card),
        "relationship_bonus_total": float(relationship),
        "selected_checking": selected_checking,
        "selected_card": selected_card,
        "expected_apy": None,
        "expected_interest": None,
        "amount_difference": None,
        "action_ready": False,
        "errors": errors,
    }
    if base is not None:
        expected_apy = base + checking + card + relationship
        output["expected_apy"] = float(expected_apy)
    else:
        expected_apy = None

    balance_fields = ("daily_balances", "days_in_year", "daily_rate_method")
    supplied_balance_fields = [key for key in balance_fields if key in data]
    exact_accrual = len(supplied_balance_fields) == len(balance_fields)
    if supplied_balance_fields and not exact_accrual:
        errors.append("daily_balances, days_in_year, and daily_rate_method must be supplied together")

    expected_interest = None
    if exact_accrual:
        balances = data.get("daily_balances")
        year_days = data.get("days_in_year")
        method = data.get("daily_rate_method")
        if not isinstance(balances, list) or not balances:
            errors.append("daily_balances must be a nonempty array")
        if not isinstance(year_days, int) or isinstance(year_days, bool) or year_days <= 0:
            errors.append("days_in_year must be a positive integer")
        if method not in ("nominal_divide_365", "effective_apy_daily"):
            errors.append("daily_rate_method must be nominal_divide_365 or effective_apy_daily")
        parsed = [decimal_value(v, f"daily_balances[{i}]", errors) for i, v in enumerate(balances)] if isinstance(balances, list) else []
        if expected_apy is not None and parsed and all(v is not None for v in parsed) and isinstance(year_days, int) and not isinstance(year_days, bool) and year_days > 0 and method in ("nominal_divide_365", "effective_apy_daily"):
            annual = expected_apy / Decimal("100")
            if method == "nominal_divide_365":
                daily_rate = annual / Decimal(year_days)
            else:
                daily_rate = (Decimal("1") + annual) ** (Decimal("1") / Decimal(year_days)) - Decimal("1")
            # Each supplied balance is an independently verified eligible end-of-day balance.
            expected_interest = sum((balance * daily_rate for balance in parsed), ZERO).quantize(CENT, rounding=ROUND_HALF_UP)
            output["expected_interest"] = float(expected_interest)

    actual_apy = None
    if "actual_apy" in data:
        actual_apy = decimal_value(data.get("actual_apy"), "actual_apy", errors)

    credit_amount = None
    credit = data.get("interest_credit")
    if credit is not None:
        if not isinstance(credit, dict):
            errors.append("interest_credit must be an object")
        else:
            if credit.get("posted") is not True:
                errors.append("interest_credit must be confirmed posted")
            credit_amount = decimal_value(credit.get("amount"), "interest_credit.amount", errors)

    if expected_interest is not None and credit_amount is not None and isinstance(credit, dict) and credit.get("posted") is True:
        difference = (expected_interest - credit_amount).quantize(CENT, rounding=ROUND_HALF_UP)
        output["amount_difference"] = float(difference)
        if actual_apy is not None and difference > ZERO:
            output["action_ready"] = True

    if expected_apy is None:
        errors.append("expected APY cannot be determined without verified base_apy")
    if expected_interest is None:
        errors.append("exact expected interest requires verified daily balances and approved daily-rate method")
    if credit is None:
        errors.append("identified posted interest_credit is required to determine a discrepancy")
    if actual_apy is None:
        errors.append("actual_apy from account or statement evidence is required for a discrepancy report")
    if output["amount_difference"] is not None and output["amount_difference"] <= 0:
        errors.append("no positive under-credit is established")

    return output


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        json.dump({"errors": [f"invalid JSON: {exc.msg}"], "action_ready": False}, sys.stdout)
        sys.stdout.write("\n")
        raise SystemExit(0)
    json.dump(main(payload), sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
