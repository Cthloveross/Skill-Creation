#!/usr/bin/env python3
"""Render a factual checking-account recommendation from caller-supplied terms.
Reads JSON from stdin and emits JSON to stdout. It does not retrieve product data.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def fail(message):
    print(json.dumps({"status": "error", "error": message}, sort_keys=True))
    raise SystemExit(0)


def amount(value, label, required=False):
    if value is None:
        if required:
            raise ValueError(label + " is required")
        return None
    if isinstance(value, bool):
        raise ValueError(label + " must be a nonnegative number")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(label + " must be a nonnegative number")
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(label + " must be a nonnegative number")
    return parsed


def dollars(value):
    return "$" + format(value.quantize(Decimal("0.01")), "f")


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    recommendation = payload.get("recommendation")
    if not isinstance(recommendation, dict):
        raise ValueError("recommendation must be an object")
    name = recommendation.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("recommendation.name must be a nonempty string")
    overdraft = amount(recommendation.get("overdraft_fee"), "recommendation.overdraft_fee", True)
    monthly = amount(recommendation.get("monthly_fee"), "recommendation.monthly_fee", True)
    waiver = amount(recommendation.get("waiver_balance"), "recommendation.waiver_balance", True)
    customer = payload.get("customer", {})
    features = payload.get("features", {})
    alternatives = payload.get("conditional_alternatives", [])
    if not isinstance(customer, dict) or not isinstance(features, dict) or not isinstance(alternatives, list):
        raise ValueError("customer and features must be objects; conditional_alternatives must be an array")
    reliable = amount(customer.get("reliable_balance"), "customer.reliable_balance")
    variable = customer.get("cash_flow_variable", False)
    if not isinstance(variable, bool):
        raise ValueError("customer.cash_flow_variable must be boolean")

    lines = ["I recommend " + name.strip() + " as the best confirmed fit for what you described."]
    if overdraft == 0:
        lines.append("It has no overdraft fee, so it meets your non-negotiable requirement.")
    else:
        lines.append("Its documented overdraft fee is " + dollars(overdraft) + ".")
    fee_line = "Its monthly maintenance fee is " + dollars(monthly) + ", waived by maintaining at least " + dollars(waiver) + " at the documented balance threshold."
    lines.append(fee_line)
    if reliable is not None:
        if reliable >= waiver:
            lines.append("Your stated reliable balance of about " + dollars(reliable) + " supports that waiver.")
        else:
            lines.append("Your stated reliable balance of about " + dollars(reliable) + " is below that waiver threshold, so the monthly fee can apply.")
    if variable:
        lines.append("Because cash flow can vary, set a balance alert at or slightly above the threshold; the maintenance fee can apply in periods when the balance falls below it.")

    rebate = amount(features.get("atm_rebate_monthly"), "features.atm_rebate_monthly")
    cashback = amount(features.get("cashback_rate"), "features.cashback_rate")
    cards = features.get("business_debit_cards")
    if rebate is not None:
        lines.append("It provides up to " + dollars(rebate) + " per month in qualifying out-of-network ATM fee rebates.")
    if cashback is not None:
        qualifier = features.get("cashback_qualifier", "eligible debit-card purchases")
        if not isinstance(qualifier, str) or not qualifier.strip():
            raise ValueError("features.cashback_qualifier must be a nonempty string")
        lines.append("It earns " + format(cashback, "f") + "% cashback on " + qualifier.strip() + ".")
    if cards is not None:
        if not isinstance(cards, int) or isinstance(cards, bool) or cards < 0:
            raise ValueError("features.business_debit_cards must be a nonnegative integer")
        lines.append("You can request up to " + str(cards) + " business debit cards for crew or team members.")
    extra = features.get("additional", [])
    if not isinstance(extra, list) or not all(isinstance(item, str) and item.strip() for item in extra):
        raise ValueError("features.additional must be an array of nonempty strings")
    for item in extra:
        lines.append(item.strip())

    for alternative in alternatives:
        if not isinstance(alternative, dict) or not isinstance(alternative.get("name"), str) or not alternative["name"].strip() or not isinstance(alternative.get("condition"), str) or not alternative["condition"].strip():
            raise ValueError("each conditional alternative needs nonempty name and condition strings")
        lines.append(alternative["name"].strip() + " is only a conditional alternative: " + alternative["condition"].strip() + ".")
    return {"status": "ok", "message": "\n\n".join(lines)}


if __name__ == "__main__":
    try:
        source = sys.stdin.read()
        if not source.strip():
            fail("stdin must contain one JSON object")
        print(json.dumps(main(json.loads(source)), sort_keys=True))
    except json.JSONDecodeError as exc:
        fail("invalid JSON: " + exc.msg)
    except ValueError as exc:
        fail(str(exc))
