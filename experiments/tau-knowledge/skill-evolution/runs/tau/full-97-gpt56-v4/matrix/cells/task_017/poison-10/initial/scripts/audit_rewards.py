#!/usr/bin/env python3
"""Audit posted reward transactions.

Reads one JSON object from stdin and writes one JSON object to stdout.  See
SKILL.md for the public schema.  This program is calculation-only and never
calls banking systems or changes customer data.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

POSTED_STATUSES = {"POSTED", "COMPLETED"}


def decimal_value(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a decimal number")
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError):
        raise ValueError(f"{field} must be a decimal number")
    if not number.is_finite():
        raise ValueError(f"{field} must be finite")
    return number


def whole_points(value, field):
    number = decimal_value(value, field)
    if number != number.to_integral_value():
        raise ValueError(f"{field} must be a whole number")
    return int(number)


def money(value):
    return format(value.quantize(Decimal("0.01")), ".2f")


def base_result():
    return {
        "ok": False,
        "audited_transactions": [],
        "manual_review": [],
        "totals": {
            "expected_points": 0,
            "recorded_points": 0,
            "net_shortfall_points": 0,
            "net_shortfall_cash": "0.00",
        },
        "errors": [],
    }


def transaction_label(transaction, index):
    identifier = transaction.get("transaction_id")
    return str(identifier) if identifier not in (None, "") else f"transaction_index_{index}"


def audit(payload):
    result = base_result()
    if not isinstance(payload, dict):
        result["errors"].append("input must be a JSON object")
        return result

    plan = payload.get("reward_plan")
    transactions = payload.get("transactions")
    if not isinstance(plan, dict):
        result["errors"].append("reward_plan must be an object")
    if not isinstance(transactions, list):
        result["errors"].append("transactions must be an array")
    if result["errors"]:
        return result

    try:
        base_percent = decimal_value(plan.get("base_percent"), "reward_plan.base_percent")
        if base_percent < 0:
            raise ValueError("reward_plan.base_percent cannot be negative")
        raw_bonus = plan.get("bonus_percent_by_category", {})
        if not isinstance(raw_bonus, dict):
            raise ValueError("reward_plan.bonus_percent_by_category must be an object")
        bonuses = {}
        for category, value in raw_bonus.items():
            rate = decimal_value(value, f"bonus rate for {category}")
            if rate < 0:
                raise ValueError(f"bonus rate for {category} cannot be negative")
            bonuses[str(category).casefold()] = rate
    except ValueError as exc:
        result["errors"].append(str(exc))
        return result

    expected_total = 0
    recorded_total = 0
    for index, transaction in enumerate(transactions):
        if not isinstance(transaction, dict):
            result["manual_review"].append({"transaction": f"transaction_index_{index}", "reason": "transaction must be an object"})
            continue
        label = transaction_label(transaction, index)
        review_reason = transaction.get("review_reason")
        if review_reason:
            result["manual_review"].append({"transaction": label, "reason": str(review_reason)})
            continue
        status = str(transaction.get("status", "")).strip().upper()
        if status not in POSTED_STATUSES:
            result["manual_review"].append({"transaction": label, "reason": "transaction is not posted or completed"})
            continue
        category = transaction.get("category")
        if not isinstance(category, str) or not category.strip():
            result["manual_review"].append({"transaction": label, "reason": "missing posted merchant category"})
            continue
        try:
            amount = decimal_value(transaction.get("transaction_amount"), f"{label}.transaction_amount")
            recorded = whole_points(transaction.get("rewards_earned"), f"{label}.rewards_earned")
            if amount < 0:
                raise ValueError(f"{label}.transaction_amount cannot be negative")
            if recorded < 0:
                raise ValueError(f"{label}.rewards_earned cannot be negative")
        except ValueError as exc:
            result["manual_review"].append({"transaction": label, "reason": str(exc)})
            continue

        rate = bonuses.get(category.strip().casefold(), base_percent)
        # percent -> decimal rate, then cash reward -> one-cent points.
        expected = int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))
        delta = expected - recorded
        expected_total += expected
        recorded_total += recorded
        result["audited_transactions"].append({
            "transaction": label,
            "merchant_name": transaction.get("merchant_name"),
            "category": category,
            "amount": money(amount),
            "applied_percent": format(rate, "f"),
            "expected_points": expected,
            "expected_cash": money(Decimal(expected) / Decimal(100)),
            "recorded_points": recorded,
            "recorded_cash": money(Decimal(recorded) / Decimal(100)),
            "discrepancy_points": delta,
            "discrepancy_cash": money(Decimal(delta) / Decimal(100)),
            "finding": "matches" if delta == 0 else ("potential_shortfall" if delta > 0 else "apparent_over_credit"),
        })

    net = expected_total - recorded_total
    result["totals"] = {
        "expected_points": expected_total,
        "recorded_points": recorded_total,
        "net_shortfall_points": net,
        "net_shortfall_cash": money(Decimal(net) / Decimal(100)),
    }
    result["ok"] = True
    return result


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        output = base_result()
        output["errors"].append(f"invalid JSON input: {exc.msg}")
        print(json.dumps(output, sort_keys=True))
        return
    print(json.dumps(audit(payload), sort_keys=True))


if __name__ == "__main__":
    main()
