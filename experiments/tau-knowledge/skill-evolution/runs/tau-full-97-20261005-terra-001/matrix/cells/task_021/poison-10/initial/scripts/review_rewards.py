#!/usr/bin/env python3
"""Deterministic reviewer for EcoCard and Business Bronze reward transactions.

Reads the JSON schema documented in SKILL.md from stdin and writes a JSON report.
No network access or account actions are performed.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_HALF_UP

BUSINESS_CARD = "business bronze rewards card"
ECO_CARD = "ecocard"
BUSINESS_ZERO = {
    "wework", "regus", "industrious", "gusto", "adp", "paychex", "rippling"
}
BUSINESS_SAAS = {"slack", "zoom", "hubspot", "salesforce"}
ECO_STANDARD = {"target", "walmart", "amazon", "thredup"}
ECO_EV_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}
POSTED_STATUSES = {"completed", "posted"}
REVERSAL_MARKERS = ("return", "credit", "refund", "reversal")


def norm(value):
    return " ".join(str(value or "").strip().lower().split())


def decimal_value(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} is required and must be numeric")
    cleaned = str(value).strip().lower().replace("$", "").replace(",", "")
    for suffix in (" points", " point"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[:-len(suffix)].strip()
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"{field} must be numeric")


def whole_points(value, mode):
    if mode == "truncate_toward_zero":
        return int(value)
    if mode == "floor":
        return int(value.to_integral_value(rounding=ROUND_FLOOR))
    if mode == "half_up":
        return int(value.to_integral_value(rounding=ROUND_HALF_UP))
    raise ValueError("rounding must be truncate_toward_zero, floor, or half_up")


def money(points):
    return format((Decimal(points) * Decimal("0.01")).quantize(Decimal("0.01")), "f")


def is_reversal(tx, amount):
    status = norm(tx.get("status"))
    return amount < 0 or any(marker in status for marker in REVERSAL_MARKERS)


def rate_for(tx):
    """Return (rate, basis, indeterminate_reason) for a non-reversal posted row."""
    card = norm(tx.get("credit_card_type"))
    merchant = norm(tx.get("merchant_name"))
    category = norm(tx.get("category"))

    if card == BUSINESS_CARD:
        if merchant in BUSINESS_ZERO:
            return Decimal("0"), "Business Bronze named merchant exclusion (0%)", None
        if merchant in BUSINESS_SAAS:
            months = tx.get("subscription_months")
            if months is None:
                return None, None, "Business Bronze SaaS subscription age is required"
            try:
                months = decimal_value(months, "subscription_months")
            except ValueError as exc:
                return None, None, str(exc)
            if months >= Decimal("12"):
                return Decimal("0"), "Business Bronze SaaS payment after initial 12 months (0%)", None
            return Decimal("1"), "Business Bronze SaaS payment within initial 12 months (1 point per dollar)", None
        return Decimal("1"), "Business Bronze eligible purchase (1 point per dollar / 1.0%)", None

    if card == ECO_CARD:
        if merchant in ECO_STANDARD:
            return Decimal("1"), "EcoCard named retailer/resale exclusion (1 point per dollar)", None
        if merchant in ECO_EV_PARTNERS:
            return Decimal("5"), "EcoCard certified EV charging partner (5 points per dollar)", None
        if category == "green":
            return Decimal("5"), "EcoCard transaction classified as qualifying Green (5 points per dollar)", None
        return Decimal("1"), "EcoCard other purchase standard rate (1 point per dollar)", None

    return None, None, "unsupported card type"


def review_one(tx, rounding):
    transaction_id = tx.get("transaction_id")
    result = {"transaction_id": transaction_id}
    required = ["transaction_id", "credit_card_type", "merchant_name", "transaction_amount", "status", "rewards_earned"]
    missing = [key for key in required if tx.get(key) in (None, "")]
    if missing:
        result.update({"review_status": "not_reviewed", "reason": "missing required fields: " + ", ".join(missing)})
        return result
    try:
        amount = decimal_value(tx["transaction_amount"], "transaction_amount")
        actual = whole_points(decimal_value(tx["rewards_earned"], "rewards_earned"), "truncate_toward_zero")
    except ValueError as exc:
        result.update({"review_status": "not_reviewed", "reason": str(exc)})
        return result

    status = norm(tx["status"])
    if status not in POSTED_STATUSES:
        result.update({"review_status": "not_reviewed", "reason": "transaction is not posted/completed", "actual_points": actual})
        return result
    if is_reversal(tx, amount):
        result.update({
            "review_status": "indeterminate",
            "reason": "return/credit requires the linked original transaction and original earn rate",
            "actual_points": actual,
        })
        return result

    rate, basis, indeterminate = rate_for(tx)
    if indeterminate:
        status_name = "not_reviewed" if indeterminate == "unsupported card type" else "indeterminate"
        result.update({"review_status": status_name, "reason": indeterminate, "actual_points": actual})
        return result

    exact = amount * rate
    expected = whole_points(exact, rounding)
    difference = expected - actual
    if difference == 0:
        review_status = "match"
    elif difference > 0:
        review_status = "possible_undercredit"
    else:
        review_status = "possible_overcredit"
    result.update({
        "review_status": review_status,
        "card_type": tx["credit_card_type"],
        "merchant_name": tx["merchant_name"],
        "amount": format(amount, "f"),
        "actual_points": actual,
        "expected_points_exact": format(exact, "f"),
        "expected_points": expected,
        "difference_points": difference,
        "difference_cash_value": money(difference),
        "basis": basis,
    })
    return result


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"input_errors": [f"invalid JSON: {exc.msg}"], "reviews": [], "anomalies": [], "summary": {}}))
        return
    if not isinstance(payload, dict):
        print(json.dumps({"input_errors": ["input must be a JSON object"], "reviews": [], "anomalies": [], "summary": {}}))
        return
    transactions = payload.get("transactions")
    rounding = payload.get("rounding", "truncate_toward_zero")
    errors = []
    if not isinstance(transactions, list):
        errors.append("transactions must be an array")
    if rounding not in {"truncate_toward_zero", "floor", "half_up"}:
        errors.append("rounding must be truncate_toward_zero, floor, or half_up")
    if errors:
        print(json.dumps({"input_errors": errors, "reviews": [], "anomalies": [], "summary": {}}))
        return

    reviews = []
    for index, tx in enumerate(transactions):
        if not isinstance(tx, dict):
            reviews.append({"transaction_id": None, "review_status": "not_reviewed", "reason": f"transaction at index {index} must be an object"})
        else:
            reviews.append(review_one(tx, rounding))

    anomalies = [r for r in reviews if r.get("review_status") in {"possible_undercredit", "possible_overcredit"}]
    comparable = [r for r in reviews if "expected_points" in r]
    summary = {
        "transactions_received": len(transactions),
        "comparable_transactions": len(comparable),
        "matches": sum(r.get("review_status") == "match" for r in reviews),
        "possible_undercredits": sum(r.get("review_status") == "possible_undercredit" for r in reviews),
        "possible_overcredits": sum(r.get("review_status") == "possible_overcredit" for r in reviews),
        "indeterminate": sum(r.get("review_status") == "indeterminate" for r in reviews),
        "not_reviewed": sum(r.get("review_status") == "not_reviewed" for r in reviews),
        "expected_points_total_for_comparable_rows": sum(r["expected_points"] for r in comparable),
        "actual_points_total_for_comparable_rows": sum(r["actual_points"] for r in comparable),
        "difference_points_total_for_comparable_rows": sum(r["difference_points"] for r in comparable),
    }
    print(json.dumps({"input_errors": [], "rounding": rounding, "reviews": reviews, "anomalies": anomalies, "summary": summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
