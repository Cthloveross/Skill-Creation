#!/usr/bin/env python3
"""Calculate comparable first-year card-return scenarios from JSON stdin.

Input and output schemas are documented in SKILL.md. The program intentionally
contains no card-specific products, dates, reward rates, or customer data.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value: Decimal) -> str:
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def decimal_value(value, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric, not boolean")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def string_list(value, field: str):
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError(f"{field} must be an array of strings")
    return value


def calculate(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("top-level JSON must be an object")
    amount = decimal_value(payload.get("purchase_amount"), "purchase_amount")
    if amount < 0:
        raise ValueError("purchase_amount must be non-negative")
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("scenarios must be a non-empty array")

    used_ids = set()
    output = []
    for index, item in enumerate(scenarios):
        prefix = f"scenarios[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{prefix} must be an object")
        scenario_id = item.get("id")
        label = item.get("label")
        if not isinstance(scenario_id, str) or not scenario_id.strip():
            raise ValueError(f"{prefix}.id must be a non-empty string")
        if scenario_id in used_ids:
            raise ValueError(f"duplicate scenario id: {scenario_id}")
        used_ids.add(scenario_id)
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"{prefix}.label must be a non-empty string")

        rate = decimal_value(item.get("rate_percent"), f"{prefix}.rate_percent")
        fee = decimal_value(item.get("first_year_fee"), f"{prefix}.first_year_fee")
        credit = decimal_value(item.get("conditional_credit", 0), f"{prefix}.conditional_credit")
        if rate < 0 or fee < 0 or credit < 0:
            raise ValueError(f"{prefix} rate, fee, and credit must be non-negative")

        gross = amount * rate / Decimal("100")
        net_without_credit = gross - fee
        net_if_credit = net_without_credit + credit
        output.append({
            "id": scenario_id,
            "label": label,
            "purchase_amount": money(amount),
            "rate_percent": str(rate.normalize()),
            "gross_reward": money(gross),
            "first_year_fee": money(fee),
            "conditional_credit": money(credit),
            "net_reward_excluding_conditional_credit": money(net_without_credit),
            "net_return_if_conditional_credit_earned": money(net_if_credit),
            "conditions": string_list(item.get("conditions"), f"{prefix}.conditions"),
            "assumptions": string_list(item.get("assumptions"), f"{prefix}.assumptions"),
        })

    by_net = sorted(output, key=lambda x: Decimal(x["net_reward_excluding_conditional_credit"]), reverse=True)
    by_conditional = sorted(output, key=lambda x: Decimal(x["net_return_if_conditional_credit_earned"]), reverse=True)
    return {
        "currency": payload.get("currency", "USD"),
        "scenarios": output,
        "ranking_excluding_conditional_credits": [x["id"] for x in by_net],
        "ranking_if_all_conditional_credits_are_earned": [x["id"] for x in by_conditional],
        "notice": "Rankings compare supplied assumptions only; they do not establish card approval, available credit, merchant acceptance, eligibility, MCC coding, or promotion enrollment.",
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(calculate(payload), ensure_ascii=False, sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
