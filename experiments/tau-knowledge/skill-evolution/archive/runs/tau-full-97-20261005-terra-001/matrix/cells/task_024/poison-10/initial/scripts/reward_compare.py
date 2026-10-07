#!/usr/bin/env python3
"""Compare card reward scenarios supplied as JSON on stdin; emit JSON on stdout."""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN

CENT = Decimal("0.01")


def dec(value, field, required=True):
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


def money(value):
    return format(value.quantize(CENT), ".2f")


def nonnegative(value, field, required=True):
    result = dec(value, field, required)
    if result is not None and result < 0:
        raise ValueError(f"{field} must not be negative")
    return result


def cap_amount(amount, cap):
    return amount if cap is None else min(amount, cap)


def scenario(card, purchase, merchant_cap, processing_percent, fixed_fee):
    name = card.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("each card.name must be a nonempty string")

    rate = nonnegative(card.get("reward_rate_percent"), f"{name}.reward_rate_percent")
    annual_fee = nonnegative(card.get("annual_fee"), f"{name}.annual_fee")
    approved_limit = nonnegative(card.get("approved_credit_limit"), f"{name}.approved_credit_limit", False)
    available_credit = nonnegative(card.get("available_credit"), f"{name}.available_credit", False)

    paid = cap_amount(purchase, merchant_cap)
    paid = cap_amount(paid, approved_limit)
    paid = cap_amount(paid, available_credit)

    warnings = []
    if merchant_cap is None:
        warnings.append("Merchant card-payment cap is unknown; result assumes the merchant can accept the calculated card-paid amount.")
    if approved_limit is None and available_credit is None:
        warnings.append("Approved limit and available credit are unknown; result does not establish that the purchase can be charged.")
    if processing_percent is None:
        warnings.append("Merchant processing surcharge is unknown; net result excludes an unconfirmed surcharge.")

    raw_transactions = card.get("transaction_amounts")
    if raw_transactions is None:
        transactions = [paid]
    else:
        if not isinstance(raw_transactions, list) or not raw_transactions:
            raise ValueError(f"{name}.transaction_amounts must be a nonempty array when supplied")
        transactions = [nonnegative(x, f"{name}.transaction_amounts") for x in raw_transactions]
        if sum(transactions, Decimal("0")) != paid:
            raise ValueError(f"{name}.transaction_amounts must total the calculated card-paid amount")

    # rate% of dollars, multiplied by 100, yields points because one point is one cent.
    points = sum(
        ((amount * rate).quantize(Decimal("0.01"), rounding=ROUND_DOWN)).to_integral_value(rounding=ROUND_DOWN)
        for amount in transactions
    )
    reward_value = points * CENT
    surcharge = None if processing_percent is None else paid * processing_percent / Decimal("100") + fixed_fee
    known_costs = annual_fee + (surcharge if surcharge is not None else Decimal("0"))
    net_without_welcome = reward_value - known_costs

    welcome_credit = nonnegative(card.get("welcome_credit", "0"), f"{name}.welcome_credit")
    welcome_status = card.get("welcome_credit_status", "unknown")
    if welcome_status not in ("qualified", "not_qualified", "unknown"):
        raise ValueError(f"{name}.welcome_credit_status must be qualified, not_qualified, or unknown")
    if welcome_status == "unknown" and welcome_credit > 0:
        warnings.append("Welcome-credit conditions are unconfirmed; do not include it in the baseline comparison.")
    if welcome_status == "qualified":
        net_if_welcome = net_without_welcome + welcome_credit
    else:
        net_if_welcome = None

    if paid < purchase:
        warnings.append("The calculated card-paid amount is below the purchase amount; the remainder requires another payment method.")

    return {
        "name": name,
        "card_paid_amount": money(paid),
        "full_purchase_chargeable": paid == purchase,
        "earned_points": str(points),
        "reward_value": money(reward_value),
        "annual_fee": money(annual_fee),
        "merchant_surcharge": None if surcharge is None else money(surcharge),
        "net_without_welcome_credit": money(net_without_welcome),
        "welcome_credit_status": welcome_status,
        "welcome_credit": money(welcome_credit),
        "net_if_welcome_credit_earned": None if net_if_welcome is None else money(net_if_welcome),
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

    results = [scenario(card, purchase, merchant_cap, processing_percent, fixed_fee) for card in cards if isinstance(card, dict)]
    if len(results) != len(cards):
        raise ValueError("each cards entry must be an object")
    ranked = [x["name"] for x in sorted(results, key=lambda x: Decimal(x["net_without_welcome_credit"]), reverse=True)]
    return {
        "purchase_amount": money(purchase),
        "calculation_basis": "Points are floored separately for each charged transaction; one point is valued at $0.01.",
        "results": results,
        "rank_by_net_without_welcome_credit": ranked,
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
