#!/usr/bin/env python3
"""Analyze posted credit-card reward records from JSON stdin.

Input and output schemas are documented in SKILL.md. This module performs no bank
operations and does not submit disputes.
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN

POSTED_STATUSES = {"COMPLETED", "POSTED"}
EXCLUDED_TERMS = {
    "fee", "fees", "interest", "balance transfer", "cash equivalent",
    "cash equivalents", "gift card", "gift cards", "person to person",
    "person-to-person", "p2p", "insurance premium", "insurance premiums",
    "refund", "refunded", "returned", "return", "reversed", "reversal",
}


def norm(value):
    return " ".join(str(value or "").strip().lower().split())


def decimal_value(value, label):
    """Parse a numeric, currency, or 'points' value without float rounding."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"missing or invalid {label}")
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    else:
        match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", str(value))
        if not match:
            raise ValueError(f"missing or invalid {label}")
        text = match.group(0).replace(",", "")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"missing or invalid {label}") from exc
    if result < 0:
        raise ValueError(f"negative {label} is not supported")
    return result


def whole_points(value):
    return int(value.to_integral_value(rounding=ROUND_DOWN))


def contains_excluded_term(category, merchant):
    text = f"{norm(category)} {norm(merchant)}"
    return any(term in text for term in EXCLUDED_TERMS)


def eco_rate(category, merchant):
    """Return points-per-dollar and a concise explanation for EcoCard."""
    cat = norm(category)
    name = norm(merchant)
    if any(excluded in name for excluded in ("target", "walmart", "amazon")):
        return Decimal("1"), "standard rate: explicit EcoCard merchant exception"

    ev_words = ("ev charging", "ev charger", "charging", "charger", "supercharger")
    is_ev = any(word in name or word in cat for word in ev_words)
    partners = ("tesla supercharger", "chargepoint", "evgo")
    if is_ev:
        if any(partner in name for partner in partners):
            return Decimal("5"), "green rate: certified EV charging network"
        return Decimal("1"), "standard rate: non-certified or unidentified EV network"

    if cat in {"green", "sustainable"}:
        return Decimal("5"), "green rate from recorded category"
    return Decimal("1"), "standard EcoCard rate"


def expected_for(transaction):
    """Return (expected_points, rule) or raise ValueError for manual review."""
    card = norm(transaction.get("credit_card_type", transaction.get("card_type")))
    category = transaction.get("category")
    merchant = transaction.get("merchant_name", "")
    amount = decimal_value(
        transaction.get("transaction_amount", transaction.get("amount")), "transaction_amount"
    )
    cat = norm(category)

    if not card:
        raise ValueError("missing card type")
    if not cat:
        raise ValueError("missing recorded category")
    if contains_excluded_term(category, merchant):
        raise ValueError("excluded, reversed, or non-purchase record")

    if card == "silver rewards card":
        rate = Decimal("0.04") if cat in {"travel", "software"} else Decimal("0.01")
        rule = "4.0% enhanced rate" if rate == Decimal("0.04") else "1.0% standard rate"
        return whole_points(amount * rate * Decimal("100")), rule

    if card == "business platinum rewards card":
        rate = Decimal("0.04") if cat in {"travel", "software", "media"} else Decimal("0.015")
        rule = "4.0% enhanced rate" if rate == Decimal("0.04") else "1.5% standard rate"
        return whole_points(amount * rate * Decimal("100")), rule

    if card == "crypto-cash back":
        return whole_points(amount * Decimal("0.02") * Decimal("100")), "2.0% eligible-purchase rate"

    if card == "ecocard":
        rate, rule = eco_rate(category, merchant)
        return whole_points(amount * rate), rule

    raise ValueError("unsupported card product")


def record_identity(transaction, index):
    value = transaction.get("transaction_id")
    return str(value) if value not in (None, "") else f"input_index_{index}"


def display_amount(value):
    return format(value.quantize(Decimal("0.01")), "f")


def analyze(transactions):
    consistent = []
    discrepancies = []
    manual_review = []

    for index, transaction in enumerate(transactions):
        if not isinstance(transaction, dict):
            manual_review.append({
                "input_index": index,
                "reason": "transaction must be a JSON object",
            })
            continue

        tx_id = record_identity(transaction, index)
        status = norm(transaction.get("status"))
        base = {
            "transaction_id": tx_id,
            "transaction_date": transaction.get("transaction_date"),
            "card_type": transaction.get("credit_card_type", transaction.get("card_type")),
            "merchant_name": transaction.get("merchant_name"),
            "category": transaction.get("category"),
        }
        if status.upper() not in POSTED_STATUSES:
            manual_review.append({**base, "reason": "transaction is not posted/completed"})
            continue

        try:
            earned = whole_points(decimal_value(
                transaction.get("rewards_earned", transaction.get("earned_points")),
                "rewards_earned",
            ))
            expected, rule = expected_for(transaction)
            amount = decimal_value(
                transaction.get("transaction_amount", transaction.get("amount")), "transaction_amount"
            )
        except ValueError as exc:
            manual_review.append({**base, "reason": str(exc)})
            continue

        details = {
            **base,
            "transaction_amount": display_amount(amount),
            "expected_points": expected,
            "earned_points": earned,
            "difference_points": expected - earned,
            "redemption_equivalent_difference_dollars": format(
                (Decimal(expected - earned) / Decimal("100")).quantize(Decimal("0.01")), "f"
            ),
            "applied_rule": rule,
        }
        if earned == expected:
            consistent.append(details)
        else:
            details["finding"] = "short_reward" if earned < expected else "over_reward"
            discrepancies.append(details)

    return {
        "summary": {
            "reviewed_count": len(transactions),
            "consistent_count": len(consistent),
            "discrepancy_count": len(discrepancies),
            "manual_review_count": len(manual_review),
        },
        "discrepancies": discrepancies,
        "consistent": consistent,
        "manual_review": manual_review,
        "calculation_notes": [
            "Expected fractional points are truncated down to whole points.",
            "A point has a $0.01 statement-credit/checking-credit value for the reviewed products.",
            "Results rely on supplied posted status, product, category, and merchant data; they do not prove merchant-code accuracy.",
        ],
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        transactions = payload.get("transactions")
        if not isinstance(transactions, list):
            raise ValueError("transactions must be a JSON array")
        output = analyze(transactions)
    except (json.JSONDecodeError, ValueError) as exc:
        output = {"input_error": str(exc)}
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
