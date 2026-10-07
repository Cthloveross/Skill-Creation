#!/usr/bin/env python3
"""Render a customer-facing account recommendation from evidence-backed inputs.

Reads one JSON object from stdin and writes one JSON object to stdout. This
program never retrieves product data and does not perform banking actions.
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


def text_field(value, label, required=False):
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be a nonempty string")
    return value.strip()


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    recommendation = payload.get("recommendation")
    if not isinstance(recommendation, dict):
        raise ValueError("recommendation must be an object")

    name = text_field(recommendation.get("name"), "recommendation.name", True)
    overdraft = amount(recommendation.get("overdraft_fee"), "recommendation.overdraft_fee", True)
    monthly = amount(recommendation.get("monthly_fee"), "recommendation.monthly_fee", True)
    waiver = amount(recommendation.get("waiver_balance"), "recommendation.waiver_balance", True)
    waiver_basis = text_field(recommendation.get("waiver_basis"), "recommendation.waiver_basis")

    customer = payload.get("customer", {})
    features = payload.get("features", {})
    alternatives = payload.get("conditional_alternatives", [])
    if not isinstance(customer, dict) or not isinstance(features, dict) or not isinstance(alternatives, list):
        raise ValueError("customer and features must be objects; conditional_alternatives must be an array")
    reliable = amount(customer.get("reliable_balance"), "customer.reliable_balance")
    variable_cash_flow = customer.get("cash_flow_variable", False)
    if not isinstance(variable_cash_flow, bool):
        raise ValueError("customer.cash_flow_variable must be boolean")

    lines = ["I recommend " + name + " as the best confirmed fit for what you described."]
    if overdraft == 0:
        lines.append("It does not assess overdraft fees, so it meets your non-negotiable zero-overdraft-fee requirement.")
    else:
        lines.append("Its documented overdraft fee is " + dollars(overdraft) + ".")

    basis_phrase = (" " + waiver_basis) if waiver_basis else ""
    lines.append(
        "Its monthly maintenance fee is " + dollars(monthly) +
        ", waived when you maintain at least " + dollars(waiver) + basis_phrase + "."
    )
    if reliable is not None:
        if reliable >= waiver:
            lines.append("Your stated reliable balance of about " + dollars(reliable) + " is above that waiver threshold.")
        else:
            lines.append("Your stated reliable balance of about " + dollars(reliable) + " is below that waiver threshold, so the monthly fee can apply.")
    if variable_cash_flow:
        lines.append(
            "Because your cash flow can vary, set a balance alert at or slightly above " +
            dollars(waiver) + "; the maintenance fee can apply in periods when the balance falls below the threshold."
        )

    rebate = amount(features.get("atm_rebate_monthly"), "features.atm_rebate_monthly")
    cashback = amount(features.get("cashback_rate"), "features.cashback_rate")
    cards = features.get("business_debit_cards")
    if rebate is not None:
        lines.append("It provides up to " + dollars(rebate) + " per month in qualifying out-of-network ATM fee rebates.")
    if cashback is not None:
        qualifier = text_field(features.get("cashback_qualifier", "eligible debit-card purchases"), "features.cashback_qualifier", True)
        lines.append("It earns " + format(cashback, "f") + "% cashback on " + qualifier + ".")
    if cards is not None:
        if not isinstance(cards, int) or isinstance(cards, bool) or cards < 0:
            raise ValueError("features.business_debit_cards must be a nonnegative integer")
        lines.append("You can request up to " + str(cards) + " business debit cards for crew or team members.")

    additional = features.get("additional", [])
    if not isinstance(additional, list) or not all(isinstance(item, str) and item.strip() for item in additional):
        raise ValueError("features.additional must be an array of nonempty strings")
    lines.extend(item.strip() for item in additional)

    for alternative in alternatives:
        if not isinstance(alternative, dict):
            raise ValueError("each conditional alternative must be an object")
        alt_name = text_field(alternative.get("name"), "conditional alternative name", True)
        condition = text_field(alternative.get("condition"), "conditional alternative condition", True)
        lines.append(alt_name + " is only a conditional alternative: " + condition + ".")

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
