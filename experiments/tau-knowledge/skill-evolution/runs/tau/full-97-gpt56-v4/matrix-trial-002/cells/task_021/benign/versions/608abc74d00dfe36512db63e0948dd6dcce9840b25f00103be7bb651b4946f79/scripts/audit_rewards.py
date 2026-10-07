#!/usr/bin/env python3
"""Audit documented Business Bronze and EcoCard transaction rewards.

Reads JSON from stdin and writes a JSON audit report to stdout. Uses only the
Python standard library and makes no account changes.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

BUSINESS_ZERO = {
    "wework", "regus", "industrious", "gusto", "adp", "paychex", "rippling"
}
BUSINESS_TIME_LIMITED = {"slack", "zoom", "hubspot", "salesforce"}
ECO_STANDARD = {"target", "walmart", "amazon", "thredup"}
ECO_CHARGING_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}


def norm(value):
    return " ".join(str(value or "").strip().casefold().split())


def as_decimal(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(field + " is missing or invalid")
    text = str(value).strip().replace(",", "")
    if text.startswith("$"):
        text = text[1:].strip()
    if text.casefold().endswith(" points"):
        text = text[:-7].strip()
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(field + " is not numeric") from exc


def floor_points(amount, multiplier):
    return int((amount * Decimal(multiplier)).to_integral_value(rounding=ROUND_FLOOR))


def subscription_age(txn, ages, merchant):
    if "subscription_age_months" in txn and txn["subscription_age_months"] is not None:
        return txn["subscription_age_months"]
    return ages.get(merchant)


def audit_one(txn, green_categories, certified_merchants, subscription_ages):
    identifier = txn.get("transaction_id")
    result = {"transaction_id": identifier, "merchant_name": txn.get("merchant_name"),
              "card_type": txn.get("credit_card_type"), "status": "not_audited"}
    if norm(txn.get("status")) not in {"completed", "posted"}:
        result["reason"] = "Transaction is not posted/completed."
        return result
    try:
        amount = as_decimal(txn.get("transaction_amount"), "transaction_amount")
        posted = as_decimal(txn.get("rewards_earned"), "rewards_earned")
    except ValueError as exc:
        result["reason"] = str(exc)
        return result
    if amount < 0:
        result["status"] = "needs_context"
        result["reason"] = "Return/credit requires the original transaction rate."
        return result
    if posted != posted.to_integral_value():
        result["reason"] = "Recorded rewards are not whole points."
        return result

    card = norm(txn.get("credit_card_type"))
    merchant = norm(txn.get("merchant_name"))
    category = norm(txn.get("category"))
    expected = None
    rate_label = None
    qualification = None

    if card == "business bronze rewards card":
        if merchant in BUSINESS_ZERO:
            expected, rate_label, qualification = 0, "0%", "named Business Bronze exclusion"
        elif merchant in BUSINESS_TIME_LIMITED:
            age = subscription_age(txn, subscription_ages, merchant)
            if age is None:
                result["status"] = "needs_context"
                result["reason"] = "Subscription age is required for this time-limited SaaS merchant."
                return result
            try:
                age = Decimal(str(age))
            except InvalidOperation:
                result["reason"] = "subscription_age_months is not numeric."
                return result
            if age > 12:
                expected, rate_label, qualification = 0, "0%", "subscription is after first 12 months"
            else:
                expected, rate_label, qualification = floor_points(amount, 1), "1.0%", "within first 12 months"
        else:
            expected, rate_label, qualification = floor_points(amount, 1), "1.0%", "eligible purchase assumption"
    elif card == "ecocard":
        if merchant in ECO_STANDARD:
            expected, rate_label, qualification = floor_points(amount, 1), "1 point/dollar", "named EcoCard standard-rate exclusion"
        elif merchant in ECO_CHARGING_PARTNERS:
            expected, rate_label, qualification = floor_points(amount, 5), "5 points/dollar", "certified EV charging network"
        elif merchant in certified_merchants:
            expected, rate_label, qualification = floor_points(amount, 5), "5 points/dollar", "confirmed certified green merchant"
        elif category in green_categories:
            expected, rate_label, qualification = floor_points(amount, 5), "5 points/dollar", "explicit qualifying green category"
        else:
            expected, rate_label, qualification = floor_points(amount, 1), "1 point/dollar", "standard EcoCard rate"
    else:
        result["status"] = "needs_context"
        result["reason"] = "Card type is outside this Skill's documented policies."
        return result

    posted_int = int(posted)
    delta = expected - posted_int
    result.update({
        "status": "discrepancy" if delta else "correct",
        "amount": format(amount, "f"),
        "rate": rate_label,
        "qualification": qualification,
        "expected_points": expected,
        "posted_points": posted_int,
        "delta_points": delta,
        "calculation": "floor(amount × applicable points-per-dollar multiplier)"
    })
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        transactions = payload["transactions"]
        if not isinstance(transactions, list):
            raise ValueError("transactions must be a list")
        green_categories = {norm(v) for v in payload.get("eco_qualifying_categories", ["Green"])}
        certified = {norm(v) for v in payload.get("eco_certified_merchants", [])}
        ages = {norm(k): v for k, v in payload.get("subscription_months_by_merchant", {}).items()}
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        print(json.dumps({"error": "Invalid input: " + str(exc)}))
        return

    results = [audit_one(t, green_categories, certified, ages) if isinstance(t, dict)
               else {"status": "not_audited", "reason": "Transaction record is not an object."}
               for t in transactions]
    auditable = [r for r in results if r["status"] in {"correct", "discrepancy"}]
    discrepancies = [r for r in results if r["status"] == "discrepancy"]
    context = [r for r in results if r["status"] == "needs_context"]
    report = {
        "results": results,
        "summary": {
            "records_received": len(results),
            "auditable_records": len(auditable),
            "correct_records": sum(r["status"] == "correct" for r in results),
            "discrepancy_count": len(discrepancies),
            "needs_context_count": len(context),
            "expected_points_total": sum(r["expected_points"] for r in auditable),
            "posted_points_total": sum(r["posted_points"] for r in auditable),
            "net_delta_points": sum(r["delta_points"] for r in auditable)
        },
        "discrepancies": discrepancies,
        "needs_context": context
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
