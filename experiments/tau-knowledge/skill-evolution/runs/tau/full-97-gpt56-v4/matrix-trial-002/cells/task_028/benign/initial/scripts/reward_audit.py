#!/usr/bin/env python3
"""Audit documented credit-card rewards.

Read JSON from stdin: {"transactions": [transaction, ...]}.
Write JSON to stdout. The program is intentionally side-effect free.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

CASHBACK_CARDS = {
    "Crypto-Cash Back",
    "Business Platinum Rewards Card",
    "Silver Rewards Card",
}
SUPPORTED_CARDS = CASHBACK_CARDS | {"EcoCard"}
EXCLUDED_CATEGORIES = {
    "fee", "fees", "interest", "cash equivalent", "cash equivalents",
    "balance transfer", "balance transfers", "person-to-person payment",
    "person to person payment", "p2p", "gift card", "gift cards",
}
SILVER_EXTRA_EXCLUSIONS = {"insurance premium", "insurance premiums"}
ECO_STANDARD_MERCHANTS = {"target", "walmart", "amazon", "thredup"}
ECO_EV_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}


def as_decimal(value):
    """Parse money represented as a number or a currency-formatted string."""
    if isinstance(value, bool) or value is None:
        raise InvalidOperation
    text = str(value).strip().replace("$", "").replace(",", "")
    return Decimal(text)


def whole_points(amount, points_per_dollar):
    return int((amount * points_per_dollar).to_integral_value(rounding=ROUND_FLOOR))


def text(value):
    return str(value or "").strip()


def normalized(value):
    return text(value).casefold()


def is_excluded(card_type, category):
    category_key = normalized(category)
    if category_key in EXCLUDED_CATEGORIES:
        return True
    return card_type == "Silver Rewards Card" and category_key in SILVER_EXTRA_EXCLUSIONS


def rate_for(transaction):
    """Return (points_per_dollar, explanation), or (None, reason) if unsupported."""
    card = text(transaction.get("credit_card_type"))
    category = text(transaction.get("category"))
    category_key = normalized(category)
    merchant_key = normalized(transaction.get("merchant_name"))

    if card not in SUPPORTED_CARDS:
        return None, "No documented rate is available for this card type."
    if is_excluded(card, category):
        return Decimal("0"), "Recorded category is a documented non-reward-earning transaction type."
    if card == "Crypto-Cash Back":
        return Decimal("2"), "Crypto-Cash Back eligible-purchase rate: 2 points per dollar (2.0%)."
    if card == "Business Platinum Rewards Card":
        if category_key in {"travel", "software", "media"}:
            return Decimal("4"), "Business Platinum enhanced category: 4 points per dollar (4.0%)."
        return Decimal("1.5"), "Business Platinum other-purchase rate: 1.5 points per dollar (1.5%)."
    if card == "Silver Rewards Card":
        if category_key in {"travel", "software"}:
            return Decimal("4"), "Silver enhanced category: 4 points per dollar (4.0%)."
        return Decimal("1"), "Silver other-purchase rate: 1 point per dollar (1.0%)."

    # EcoCard
    if merchant_key in ECO_STANDARD_MERCHANTS:
        return Decimal("1"), "EcoCard documented merchant exclusion: 1 sustainability point per dollar."
    if "charging" in category_key or "ev charging" in category_key:
        if merchant_key in ECO_EV_PARTNERS:
            return Decimal("5"), "EcoCard certified EV-charging partner: 5 sustainability points per dollar."
        return Decimal("1"), "EcoCard non-partner EV charging: 1 sustainability point per dollar."
    if category_key == "green":
        return Decimal("5"), "EcoCard recorded qualifying Green category: 5 sustainability points per dollar."
    return Decimal("1"), "EcoCard other-purchase rate: 1 sustainability point per dollar."


def audit_one(transaction):
    """Return (bucket, result), where bucket is audited, skipped, or input_error."""
    if not isinstance(transaction, dict):
        return "input_error", {"reason": "Transaction must be a JSON object."}
    transaction_id = text(transaction.get("transaction_id"))
    if not transaction_id:
        return "input_error", {"reason": "Missing transaction_id."}

    status = normalized(transaction.get("status"))
    try:
        amount = as_decimal(transaction.get("transaction_amount"))
    except (InvalidOperation, ValueError):
        return "input_error", {"transaction_id": transaction_id, "reason": "Invalid transaction_amount."}
    if status != "completed":
        return "skipped", {"transaction_id": transaction_id, "reason": "Only COMPLETED posted purchases are audited.", "status": text(transaction.get("status"))}
    if amount <= 0:
        return "skipped", {"transaction_id": transaction_id, "reason": "Non-positive amount may be a credit, return, or non-purchase; net reward treatment cannot be confirmed."}
    try:
        recorded = int(transaction.get("rewards_earned"))
    except (TypeError, ValueError):
        return "input_error", {"transaction_id": transaction_id, "reason": "Invalid or missing rewards_earned."}

    rate, explanation = rate_for(transaction)
    if rate is None:
        return "skipped", {"transaction_id": transaction_id, "reason": explanation, "card_type": text(transaction.get("credit_card_type"))}
    expected = whole_points(amount, rate)
    difference = expected - recorded
    card = text(transaction.get("credit_card_type"))
    result = {
        "transaction_id": transaction_id,
        "transaction_date": text(transaction.get("transaction_date")),
        "card_type": card,
        "merchant_name": text(transaction.get("merchant_name")),
        "category": text(transaction.get("category")),
        "amount": format(amount, "f"),
        "recorded_points": recorded,
        "expected_points": expected,
        "points_short": difference,
        "dollar_equivalent_difference": format(Decimal(difference) / Decimal("100"), ".2f"),
        "points_unit": "sustainability points" if card == "EcoCard" else "cash-back points",
        "points_per_dollar": format(rate, "f"),
        "calculation_basis": explanation,
        "matches": difference == 0,
    }
    return "audited", result


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "Input must be valid JSON.", "detail": str(exc)}))
        return
    transactions = payload.get("transactions") if isinstance(payload, dict) else None
    if not isinstance(transactions, list):
        print(json.dumps({"error": "Input object must contain a transactions array."}))
        return

    audited, skipped, input_errors = [], [], []
    for transaction in transactions:
        bucket, result = audit_one(transaction)
        if bucket == "audited":
            audited.append(result)
        elif bucket == "skipped":
            skipped.append(result)
        else:
            input_errors.append(result)
    discrepancies = [item for item in audited if not item["matches"]]
    cash_difference = sum(item["points_short"] for item in discrepancies if item["card_type"] != "EcoCard")
    eco_difference = sum(item["points_short"] for item in discrepancies if item["card_type"] == "EcoCard")
    output = {
        "audited": audited,
        "discrepancies": discrepancies,
        "skipped": skipped,
        "input_errors": input_errors,
        "summary": {
            "transactions_received": len(transactions),
            "transactions_audited": len(audited),
            "matching_transactions": len(audited) - len(discrepancies),
            "discrepancies_found": len(discrepancies),
            "cash_back_card_points_short_total": cash_difference,
            "cash_back_card_dollar_equivalent_total": format(Decimal(cash_difference) / Decimal("100"), ".2f"),
            "ecocard_sustainability_points_short_total": eco_difference,
            "ecocard_dollar_equivalent_total": format(Decimal(eco_difference) / Decimal("100"), ".2f"),
            "skipped_transactions": len(skipped),
            "input_errors": len(input_errors),
        },
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
