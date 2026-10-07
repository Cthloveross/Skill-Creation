#!/usr/bin/env python3
"""Audit Business Bronze and EcoCard reward points.

Read one JSON object from stdin.  Write one JSON audit object to stdout.
See SKILL.md for the input schema and policy assumptions.
"""
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

BRONZE = "business bronze rewards card"
ECO = "ecocard"
BRONZE_ZERO = {
    "wework", "regus", "industrious", "gusto", "adp", "paychex", "rippling"
}
BRONZE_SAAS = {"slack", "zoom", "hubspot", "salesforce"}
ECO_STANDARD = {"target", "walmart", "amazon", "thredup"}
ECO_GREEN = {"tesla supercharger", "chargepoint", "evgo"}


def normalized(value):
    """Normalize a known merchant/card/category label for exact rule matching."""
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def integer_points(value):
    """Accept an integral JSON number or a display string such as '42 points'."""
    if isinstance(value, bool):
        raise ValueError("boolean is not a point count")
    if isinstance(value, int):
        return value
    text = str(value).strip().lower().replace(",", "")
    match = re.search(r"-?\d+", text)
    if not match:
        raise ValueError("missing or invalid rewards_earned")
    return int(match.group(0))


def amount_decimal(value):
    """Parse a non-localized transaction amount without binary floating point."""
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError("missing or invalid transaction_amount")


def floor_points(value):
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def manual(txn, reason):
    return {
        "transaction_id": txn.get("transaction_id"),
        "card_type": txn.get("credit_card_type"),
        "merchant_name": txn.get("merchant_name"),
        "status": txn.get("status"),
        "reason": reason,
    }


def expected_for(txn, green_category_means_qualified):
    """Return (expected_points, policy_basis) or raise ValueError for manual review."""
    amount = amount_decimal(txn.get("transaction_amount"))
    if amount <= 0:
        raise ValueError("non-positive amount needs original-transaction/reversal review")
    if normalized(txn.get("status")) != "completed":
        raise ValueError("only completed positive purchases are automatically auditable")

    card = normalized(txn.get("credit_card_type"))
    merchant = normalized(txn.get("merchant_name"))
    if card == BRONZE:
        if merchant in BRONZE_ZERO:
            return 0, "Business Bronze excluded merchant: 0 points"
        if merchant in BRONZE_SAAS:
            months = txn.get("subscription_months")
            if months is None:
                raise ValueError("SaaS subscription age is required for this merchant")
            try:
                months = Decimal(str(months))
            except InvalidOperation:
                raise ValueError("invalid subscription_months")
            if months < 0:
                raise ValueError("invalid subscription_months")
            if months > 12:
                return 0, "Business Bronze SaaS subscription after first 12 months: 0 points"
        return floor_points(amount), "Business Bronze eligible purchase: 1 point per dollar, rounded down"

    if card == ECO:
        if merchant in ECO_STANDARD:
            qualified = False
            basis = "EcoCard named merchant exclusion: standard 1 point per dollar"
        elif merchant in ECO_GREEN:
            qualified = True
            basis = "EcoCard certified EV charging network: 5 points per dollar"
        elif txn.get("green_qualified") is True:
            qualified = True
            basis = "EcoCard supplied green qualification: 5 points per dollar"
        elif green_category_means_qualified and normalized(txn.get("category")) == "green":
            qualified = True
            basis = "EcoCard Green category qualification: 5 points per dollar"
        else:
            qualified = False
            basis = "EcoCard standard purchase: 1 point per dollar"
        rate = Decimal("5") if qualified else Decimal("1")
        return floor_points(amount * rate), basis + ", rounded down"

    raise ValueError("unsupported card type")


def audit(payload):
    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        raise ValueError("transactions must be an array")
    green_category_means_qualified = payload.get("green_category_means_qualified", True)
    if not isinstance(green_category_means_qualified, bool):
        raise ValueError("green_category_means_qualified must be boolean")

    audited = []
    manual_review = []
    for txn in transactions:
        if not isinstance(txn, dict):
            manual_review.append({"transaction_id": None, "reason": "transaction is not an object"})
            continue
        try:
            expected, basis = expected_for(txn, green_category_means_qualified)
            posted = integer_points(txn.get("rewards_earned"))
            difference = expected - posted
            audited.append({
                "transaction_id": txn.get("transaction_id"),
                "transaction_date": txn.get("transaction_date"),
                "card_type": txn.get("credit_card_type"),
                "merchant_name": txn.get("merchant_name"),
                "amount": str(amount_decimal(txn.get("transaction_amount"))),
                "posted_points": posted,
                "expected_points": expected,
                "difference_points": difference,
                "difference_cash_value": format(Decimal(difference) * Decimal("0.01"), ".2f"),
                "policy_basis": basis,
                "result": "match" if difference == 0 else "discrepancy",
            })
        except ValueError as exc:
            manual_review.append(manual(txn, str(exc)))

    discrepancies = [row for row in audited if row["result"] == "discrepancy"]
    return {
        "audited_transactions": audited,
        "manual_review": manual_review,
        "summary": {
            "input_transaction_count": len(transactions),
            "audited_count": len(audited),
            "manual_review_count": len(manual_review),
            "matching_count": len(audited) - len(discrepancies),
            "discrepancy_count": len(discrepancies),
            "total_expected_minus_posted_points": sum(r["difference_points"] for r in audited),
            "total_expected_minus_posted_cash_value": format(
                Decimal(sum(r["difference_points"] for r in audited)) * Decimal("0.01"), ".2f"
            ),
        },
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(audit(payload), ensure_ascii=False, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
