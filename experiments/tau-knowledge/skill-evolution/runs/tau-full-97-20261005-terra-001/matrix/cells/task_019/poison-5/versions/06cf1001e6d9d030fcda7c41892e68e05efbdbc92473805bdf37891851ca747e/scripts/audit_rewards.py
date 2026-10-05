#!/usr/bin/env python3
"""Audit Gold Rewards Card and EcoCard transaction rewards.

Input: JSON object with a `transactions` list. Output: JSON audit report.
Uses only the Python standard library and does not access banking systems.
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

GOLD = "gold rewards card"
ECO = "ecocard"
EXCLUDED_MERCHANT_TOKENS = ("target", "walmart", "amazon", "thredup")
EV_PARTNER_TOKENS = ("tesla supercharger", "chargepoint", "evgo")
EV_CHARGING_TOKENS = ("charging", "charger", "supercharger", "chargepoint", "evgo")


def normalized(value):
    return " ".join(str(value or "").casefold().split())


def first_number(value, field):
    """Parse a non-negative decimal from a numeric field or display string."""
    if isinstance(value, bool) or value is None:
        raise ValueError("missing or invalid %s" % field)
    if isinstance(value, (int, float, Decimal)):
        raw = str(value)
    elif isinstance(value, str):
        raw = value.replace(",", "")
    else:
        raise ValueError("missing or invalid %s" % field)
    match = re.search(r"-?\d+(?:\.\d+)?", raw)
    if not match:
        raise ValueError("missing or invalid %s" % field)
    try:
        parsed = Decimal(match.group(0))
    except InvalidOperation as exc:
        raise ValueError("missing or invalid %s" % field) from exc
    if parsed < 0:
        raise ValueError("%s cannot be negative" % field)
    return parsed


def whole_points(amount, multiplier):
    return int((amount * Decimal(multiplier)).to_integral_value(rounding=ROUND_FLOOR))


def eco_rate(category, merchant):
    """Return (multiplier, human-readable eligibility explanation)."""
    merchant_key = normalized(merchant)
    category_key = normalized(category)

    if any(token in merchant_key for token in EXCLUDED_MERCHANT_TOKENS):
        return 1, "documented EcoCard merchant exclusion; standard rate"

    is_charging = any(token in merchant_key for token in EV_CHARGING_TOKENS)
    if is_charging:
        if any(token in merchant_key for token in EV_PARTNER_TOKENS):
            return 5, "certified EV charging partner; enhanced green rate"
        return 1, "EV charging network is not a documented certified partner; standard rate"

    if category_key == "green" or "green" in category_key or "sustainable" in category_key:
        return 5, "transaction is labeled Green/Sustainable and no documented exclusion applies"
    return 1, "not labeled as a qualifying green purchase; standard rate"


def audit_transaction(transaction, index):
    tx_id = transaction.get("transaction_id")
    tx_id = str(tx_id).strip() if tx_id is not None else ""
    card = transaction.get("credit_card_type", transaction.get("card_type"))
    card_key = normalized(card)
    status = normalized(transaction.get("status", "COMPLETED"))
    merchant = transaction.get("merchant_name", "")
    category = transaction.get("category", "")

    base = {
        "index": index,
        "transaction_id": tx_id or None,
        "card_type": card,
        "merchant_name": merchant or None,
        "category": category or None,
        "status": transaction.get("status", "COMPLETED"),
    }
    if not tx_id:
        base.update({"result": "review_required", "reason": "missing transaction_id"})
        return base
    if status != "completed":
        base.update({
            "result": "skipped",
            "reason": "transaction is not completed; posted rewards should not be audited as final",
        })
        return base
    if card_key not in (GOLD, ECO):
        base.update({
            "result": "review_required",
            "reason": "unsupported card type; this Skill covers Gold Rewards Card and EcoCard only",
        })
        return base

    try:
        amount = first_number(
            transaction.get("transaction_amount", transaction.get("amount")), "transaction_amount"
        )
        recorded = int(first_number(transaction.get("rewards_earned"), "rewards_earned"))
    except ValueError as exc:
        base.update({"result": "review_required", "reason": str(exc)})
        return base

    if card_key == GOLD:
        multiplier = 2.5
        eligibility = "Gold Rewards Card earns 2.5% cash back on all purchases"
    else:
        multiplier, eligibility = eco_rate(category, merchant)

    expected = whole_points(amount, multiplier)
    delta = expected - recorded
    if delta == 0:
        result = "match"
    elif delta > 0:
        result = "under_awarded"
    else:
        result = "over_awarded"

    base.update({
        "result": result,
        "transaction_amount": format(amount, "f"),
        "recorded_points": recorded,
        "expected_points": expected,
        "point_difference_expected_minus_recorded": delta,
        "cash_value_difference_dollars": format(Decimal(abs(delta)) * Decimal("0.01"), ".2f"),
        "rate_points_per_dollar": str(multiplier),
        "eligibility_basis": eligibility,
        "rounding": "floor to a whole point",
        "calculation": "floor(%s x %s) = %d points" % (format(amount, "f"), multiplier, expected),
    })
    return base


def audit(payload):
    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        return {
            "error": "input must be an object containing a transactions array",
            "transactions": [],
            "discrepancies": [],
            "review_required": [],
        }

    rows = [audit_transaction(item, i) if isinstance(item, dict) else {
        "index": i, "transaction_id": None, "result": "review_required",
        "reason": "transaction entry must be an object"
    } for i, item in enumerate(transactions)]
    discrepancies = [r for r in rows if r["result"] in ("under_awarded", "over_awarded")]
    review_required = [r for r in rows if r["result"] == "review_required"]
    skipped = [r for r in rows if r["result"] == "skipped"]
    matched = [r for r in rows if r["result"] == "match"]
    return {
        "transactions": rows,
        "discrepancies": discrepancies,
        "review_required": review_required,
        "summary": {
            "input_count": len(rows),
            "reviewed_count": len(rows) - len(review_required) - len(skipped),
            "matched_count": len(matched),
            "discrepancy_count": len(discrepancies),
            "review_required_count": len(review_required),
            "skipped_count": len(skipped),
        },
        "next_step": (
            "Explain apparent differences; do not alter rewards. If the customer wants to dispute a "
            "specific discrepancy, provide the customer-facing cash-back dispute tool with their user ID "
            "and that transaction ID."
        ),
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        json.dump({"error": "invalid JSON input: %s" % exc}, sys.stdout)
        return
    if not isinstance(payload, dict):
        json.dump({"error": "input JSON must be an object"}, sys.stdout)
        return
    json.dump(audit(payload), sys.stdout, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
