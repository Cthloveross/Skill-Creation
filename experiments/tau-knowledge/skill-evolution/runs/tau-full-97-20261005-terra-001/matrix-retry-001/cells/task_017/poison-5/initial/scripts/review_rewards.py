#!/usr/bin/env python3
"""Review supported Silver Rewards Card bonus-category rewards.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
is deliberately calculation-only: it does not access accounts, disputes, or tools,
and its correction candidates are not authorization to perform an update.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN

SUPPORTED_CARD = "Silver Rewards Card"
BONUS_CATEGORIES = {"travel", "software"}
EXCLUSION_FIELDS = (
    "returned_or_refunded",
    "is_gift_card",
    "is_p2p",
    "is_fee",
    "is_interest",
    "is_insurance_premium",
)


def as_decimal(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("transaction_amount must be a decimal amount")
    try:
        amount = Decimal(str(value).strip().replace("$", "").replace(",", ""))
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError("transaction_amount must be a decimal amount") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("transaction_amount must be a non-negative finite amount")
    return amount


def as_points(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("rewards_earned is required")
    text = str(value).strip().lower()
    if text.endswith("points"):
        text = text[:-6].strip()
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("rewards_earned must be a whole-point value") from exc
    if not number.is_finite() or number != number.to_integral_value() or number < 0:
        raise ValueError("rewards_earned must be a non-negative whole-point value")
    return int(number)


def error_result(message):
    return {"ok": False, "error": message, "reviews": [], "approved_corrections": []}


def main(payload):
    if not isinstance(payload, dict):
        return error_result("input must be a JSON object")
    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        return error_result("transactions must be a JSON array")
    resolved_ids = payload.get("resolved_dispute_transaction_ids", [])
    if not isinstance(resolved_ids, list) or not all(isinstance(x, str) and x for x in resolved_ids):
        return error_result("resolved_dispute_transaction_ids must be an array of nonempty strings")
    resolved_ids = set(resolved_ids)
    card_type = payload.get("card_type")
    reviews = []
    approved = []

    for index, txn in enumerate(transactions):
        if not isinstance(txn, dict):
            return error_result("transactions[%d] must be an object" % index)
        transaction_id = txn.get("transaction_id")
        if not isinstance(transaction_id, str) or not transaction_id:
            return error_result("transactions[%d].transaction_id must be a nonempty string" % index)
        category_value = txn.get("category")
        status_value = txn.get("status")
        if not isinstance(category_value, str) or not isinstance(status_value, str):
            return error_result("transactions[%d] requires string category and status" % index)
        try:
            actual = as_points(txn.get("rewards_earned"))
            amount = as_decimal(txn.get("transaction_amount"))
        except ValueError as exc:
            return error_result("transactions[%d]: %s" % (index, exc))

        category = category_value.strip().lower()
        status = status_value.strip().upper()
        exclusions = [field for field in EXCLUSION_FIELDS if txn.get(field, False) is True]
        base = {
            "transaction_id": transaction_id,
            "actual_points": actual,
            "category": category_value,
            "status": status_value,
        }

        if card_type != SUPPORTED_CARD:
            base.update({
                "outcome": "unsupported_card",
                "reason": "No documented rate is available in this helper for the supplied card type.",
            })
        elif status != "COMPLETED":
            base.update({
                "outcome": "not_final",
                "reason": "Rewards are calculated after a transaction posts/completes.",
            })
        elif exclusions:
            base.update({
                "outcome": "ineligible_or_reversed",
                "expected_points": 0,
                "reason": "Known exclusion flags: " + ", ".join(exclusions),
            })
        elif category not in BONUS_CATEGORIES:
            base.update({
                "outcome": "unsupported_rate",
                "reason": "The documented Silver bonus rate applies only to Travel and Software; no base rate is assumed.",
            })
        else:
            # 4.0% cash back at one point per cent is 4 points per dollar.
            expected = int((amount * Decimal("4")).to_integral_value(rounding=ROUND_DOWN))
            base["expected_points"] = expected
            base["formula"] = "floor(transaction_amount * 4)"
            if actual == expected:
                base["outcome"] = "matches_documented_rate"
            else:
                base["outcome"] = "discrepancy"
                base["difference_points"] = expected - actual
                if transaction_id in resolved_ids:
                    correction = {
                        "transaction_id": transaction_id,
                        "old_rewards_earned": "%d points" % actual,
                        "new_rewards_earned": "%d points" % expected,
                        "expected_points": expected,
                        "basis": "resolved dispute ID supplied; independently calculated documented Silver 4% Travel/Software rate",
                    }
                    approved.append(correction)
                    base["resolved_dispute_id_supplied"] = True
                else:
                    base["resolved_dispute_id_supplied"] = False
        reviews.append(base)

    return {
        "ok": True,
        "card_type": card_type,
        "reviews": reviews,
        "approved_corrections": approved,
        "notice": "Correction candidates require independent confirmation of a resolved dispute, account ownership, and post-update verification before any tool call.",
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), separators=(",", ":"), sort_keys=True))
    except json.JSONDecodeError:
        print(json.dumps(error_result("stdin must contain valid JSON"), separators=(",", ":"), sort_keys=True))
    except Exception as exc:  # Keep the script protocol JSON-only on unexpected invalid input.
        print(json.dumps(error_result("unexpected input error: %s" % exc), separators=(",", ":"), sort_keys=True))
