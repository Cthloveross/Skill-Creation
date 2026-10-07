#!/usr/bin/env python3
"""Compare supplied large-purchase card scenarios from JSON stdin and emit JSON stdout."""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN

CENT = Decimal("0.01")


def decimal_value(value, field, required=True):
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a decimal number, not boolean")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal number")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def nonnegative(value, field, required=True):
    result = decimal_value(value, field, required)
    if result is not None and result < 0:
        raise ValueError(f"{field} must not be negative")
    return result


def money(value):
    return format(value.quantize(CENT), ".2f")


def limit_charge(amount, limit):
    return amount if limit is None else min(amount, limit)


def calculate_scenario(card, purchase, merchant_cap, processing_percent, fixed_fee):
    if not isinstance(card, dict):
        raise ValueError("each cards entry must be an object")
    name = card.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("each card.name must be a nonempty string")

    rate = nonnegative(card.get("reward_rate_percent"), f"{name}.reward_rate_percent")
    annual_fee = nonnegative(card.get("annual_fee"), f"{name}.annual_fee")
    approved_limit = nonnegative(card.get("approved_credit_limit"), f"{name}.approved_credit_limit", False)
    available_credit = nonnegative(card.get("available_credit"), f"{name}.available_credit", False)

    paid = limit_charge(limit_charge(limit_charge(purchase, merchant_cap), approved_limit), available_credit)
    warnings = []
    if merchant_cap is None:
        warnings.append("Merchant card-payment cap is unknown; this does not establish merchant acceptance.")
    if approved_limit is None and available_credit is None:
        warnings.append("Approved limit and available credit are unknown; this does not establish charge capacity.")
    if processing_percent is None:
        warnings.append("Merchant processing surcharge is unknown; net result excludes an unconfirmed surcharge.")

    raw_transactions = card.get("transaction_amounts")
    if raw_transactions is None:
        transactions = [paid]
    else:
        if not isinstance(raw_transactions, list) or not raw_transactions:
            raise ValueError(f"{name}.transaction_amounts must be a nonempty array when supplied")
        transactions = [nonnegative(item, f"{name}.transaction_amounts") for item in raw_transactions]
        if sum(transactions, Decimal("0")) != paid:
            raise ValueError(f"{name}.transaction_amounts must total the calculated card-paid amount")

    # A rate expressed as percent times dollars gives whole cents/points.
    points = sum(
        (amount * rate).to_integral_value(rounding=ROUND_DOWN)
        for amount in transactions
    )
    reward_value = points * CENT
    surcharge = None
    if processing_percent is not None:
        surcharge = paid * processing_percent / Decimal("100") + fixed_fee
    known_costs = annual_fee + (surcharge if surcharge is not None else Decimal("0"))
    ordinary_net = reward_value - known_costs

    welcome_credit = nonnegative(card.get("welcome_credit", "0"), f"{name}.welcome_credit")
    welcome_status = card.get("welcome_credit_status", "unknown")
    if welcome_status not in {"qualified", "not_qualified", "unknown"}:
        raise ValueError(f"{name}.welcome_credit_status must be qualified, not_qualified, or unknown")
    if welcome_status == "unknown" and welcome_credit > 0:
        warnings.append("Welcome-credit conditions are unconfirmed; exclude it from the baseline comparison.")
    conditional_net = ordinary_net + welcome_credit if welcome_status == "qualified" else None

    if paid < purchase:
        warnings.append("The calculated card-paid amount is below the purchase amount; another payment method is required for the remainder.")

    return {
        "name": name,
        "card_paid_amount": money(paid),
        "full_purchase_chargeable": paid == purchase,
        "earned_points": str(points),
        "reward_value": money(reward_value),
        "annual_fee": money(annual_fee),
        "merchant_surcharge": None if surcharge is None else money(surcharge),
        "net_without_welcome_credit": money(ordinary_net),
        "welcome_credit_status": welcome_status,
        "welcome_credit": money(welcome_credit),
        "net_if_welcome_credit_earned": None if conditional_net is None else money(conditional_net),
        "warnings": warnings,
    }


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    purchase = nonnegative(payload.get("purchase_amount"), "purchase_amount")
    if purchase <= 0:
        raise ValueError("purchase_amount must be greater than zero")
    merchant_cap = nonnegative(payload.get("merchant_card_cap"), "merchant_card_cap", False)
    processing_percent = nonnegative(payload.get("merchant_processing_percent"), "merchant_processing_percent", False)
    fixed_fee = nonnegative(payload.get("merchant_fixed_fee", "0"), "merchant_fixed_fee")
    cards = payload.get("cards")
    if not isinstance(cards, list) or not cards:
        raise ValueError("cards must be a nonempty array")

    results = [calculate_scenario(card, purchase, merchant_cap, processing_percent, fixed_fee) for card in cards]
    ranked = [
        item["name"]
        for item in sorted(results, key=lambda item: Decimal(item["net_without_welcome_credit"]), reverse=True)
    ]
    return {
        "purchase_amount": money(purchase),
        "calculation_basis": "Points are floored separately for each charged transaction; one point is valued at $0.01.",
        "results": results,
        "rank_by_net_without_welcome_credit": ranked,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
