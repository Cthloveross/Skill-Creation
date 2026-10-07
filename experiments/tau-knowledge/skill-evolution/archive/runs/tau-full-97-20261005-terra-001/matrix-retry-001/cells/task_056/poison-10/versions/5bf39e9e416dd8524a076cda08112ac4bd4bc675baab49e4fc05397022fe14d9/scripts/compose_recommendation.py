#!/usr/bin/env python3
"""Render a direct customer-facing recommendation from evidence-backed JSON.

Reads one JSON object from stdin and writes one JSON object to stdout. It never
retrieves product data and never performs a banking action.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def error(message):
    print(json.dumps({"status": "error", "error": message}, sort_keys=True))
    raise SystemExit(0)


def text(value, label, required=False):
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be a nonempty string")
    return value.strip()


def number(value, label, required=False):
    if value is None:
        if required:
            raise ValueError(label + " is required")
        return None
    if isinstance(value, bool):
        raise ValueError(label + " must be a nonnegative number")
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(label + " must be a nonnegative number")
    if not value.is_finite() or value < 0:
        raise ValueError(label + " must be a nonnegative number")
    return value


def money(value):
    return "$" + format(value.quantize(Decimal("0.01")), "f")


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    rec = payload.get("recommendation")
    if not isinstance(rec, dict):
        raise ValueError("recommendation must be an object")

    name = text(rec.get("name"), "recommendation.name", True)
    overdraft = number(rec.get("overdraft_fee"), "recommendation.overdraft_fee", True)
    monthly = number(rec.get("monthly_fee"), "recommendation.monthly_fee", True)
    waiver = number(rec.get("waiver_balance"), "recommendation.waiver_balance", True)
    basis = text(rec.get("waiver_basis"), "recommendation.waiver_basis")

    customer = payload.get("customer", {})
    features = payload.get("features", {})
    alternatives = payload.get("conditional_alternatives", [])
    if not isinstance(customer, dict) or not isinstance(features, dict):
        raise ValueError("customer and features must be objects")
    if not isinstance(alternatives, list):
        raise ValueError("conditional_alternatives must be an array")

    reliable = number(customer.get("reliable_balance"), "customer.reliable_balance")
    variable = customer.get("cash_flow_variable", False)
    if not isinstance(variable, bool):
        raise ValueError("customer.cash_flow_variable must be boolean")

    lines = ["I recommend " + name + " as the best confirmed fit for what you described."]
    if overdraft == 0:
        lines.append("It does not assess overdraft fees, so it meets your zero-overdraft-fee requirement.")
    else:
        lines.append("Its documented overdraft fee is " + money(overdraft) + ".")

    threshold = " " + basis if basis else ""
    lines.append("Its monthly maintenance fee is " + money(monthly) + ", waived when you maintain at least " + money(waiver) + threshold + ".")
    if reliable is not None:
        if reliable >= waiver:
            lines.append("Your stated reliable balance of about " + money(reliable) + " is above that waiver threshold.")
        else:
            lines.append("Your stated reliable balance of about " + money(reliable) + " is below that waiver threshold, so the monthly fee can apply.")
    if variable:
        lines.append("Because your cash flow can vary, set a balance alert at or slightly above " + money(waiver) + "; the maintenance fee can apply when the balance falls below the threshold.")

    rebate = number(features.get("atm_rebate_monthly"), "features.atm_rebate_monthly")
    cashback = number(features.get("cashback_rate"), "features.cashback_rate")
    cards = features.get("business_debit_cards")
    if rebate is not None:
        lines.append("It provides up to " + money(rebate) + " per month in qualifying out-of-network ATM-fee rebates; fees above that monthly cap would not be rebated.")
    if cashback is not None:
        qualifier = text(features.get("cashback_qualifier", "eligible debit-card purchases"), "features.cashback_qualifier", True)
        lines.append("It earns " + format(cashback, "f") + "% cashback on " + qualifier + ".")
    if cards is not None:
        if not isinstance(cards, int) or isinstance(cards, bool) or cards < 0:
            raise ValueError("features.business_debit_cards must be a nonnegative integer")
        lines.append("You can request up to " + str(cards) + " business debit cards for team members.")

    additional = features.get("additional", [])
    if not isinstance(additional, list) or not all(isinstance(item, str) and item.strip() for item in additional):
        raise ValueError("features.additional must be an array of nonempty strings")
    lines.extend(item.strip() for item in additional)

    for alternative in alternatives:
        if not isinstance(alternative, dict):
            raise ValueError("each conditional alternative must be an object")
        alt_name = text(alternative.get("name"), "conditional alternative name", True)
        condition = text(alternative.get("condition"), "conditional alternative condition", True)
        lines.append(alt_name + " is only a conditional alternative: " + condition + ".")

    return {"status": "ok", "message": "\n\n".join(lines)}


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            error("stdin must contain one JSON object")
        print(json.dumps(main(json.loads(raw)), sort_keys=True))
    except json.JSONDecodeError as exc:
        error("invalid JSON: " + exc.msg)
    except ValueError as exc:
        error(str(exc))
