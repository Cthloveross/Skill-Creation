#!/usr/bin/env python3
"""Deterministic audit for Business Bronze Rewards Card and EcoCard transactions.

Input: JSON object described in SKILL.md on stdin.
Output: JSON object containing calculated audit rows; no account actions are taken.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN

BRONZE = "business bronze rewards card"
ECO = "ecocard"
BRONZE_ZERO = {
    "wework", "regus", "industrious", "gusto", "adp", "paychex", "rippling"
}
SAAS = {"slack", "zoom", "hubspot", "salesforce"}
ECO_STANDARD = {"target", "walmart", "amazon", "thredup"}
GREEN_EV = {"tesla supercharger", "chargepoint", "evgo"}
POSTED = {"completed", "posted"}
REVERSALS = {"returned", "return", "refunded", "refund", "credited", "credit"}


def normalized(value):
    return " ".join(str(value or "").strip().casefold().split())


def money(value):
    if isinstance(value, bool):
        raise ValueError("amount cannot be boolean")
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("invalid transaction_amount") from exc


def whole_points(amount, rate):
    """Truncate fractional points toward zero, including a negative reversal."""
    return int((amount * rate).to_integral_value(rounding=ROUND_DOWN))


def actual_points(value):
    if isinstance(value, bool):
        raise ValueError("rewards_earned cannot be boolean")
    try:
        parsed = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError("invalid rewards_earned") from exc
    if parsed != parsed.to_integral_value():
        raise ValueError("rewards_earned must be a whole number of points")
    return int(parsed)


def rate_for_purchase(txn, subscriptions):
    card = normalized(txn.get("credit_card_type"))
    merchant = normalized(txn.get("merchant_name"))
    category = normalized(txn.get("category"))

    if card == BRONZE:
        if merchant in BRONZE_ZERO:
            return Decimal("0"), "Business Bronze excluded merchant (0-point rate)", None
        if merchant in SAAS:
            months = subscriptions.get(merchant)
            if months is None:
                return None, None, "SaaS subscription duration is required to determine whether the first 12 months have elapsed"
            try:
                months = Decimal(str(months))
            except InvalidOperation:
                return None, None, "SaaS subscription duration is invalid"
            if months < 0:
                return None, None, "SaaS subscription duration cannot be negative"
            if months > Decimal("12"):
                return Decimal("0"), "Business Bronze SaaS subscription is beyond its first 12 months (0-point rate)", None
            return Decimal("1"), "Business Bronze eligible purchase during first 12 SaaS subscription months (1 point per dollar)", None
        return Decimal("1"), "Business Bronze eligible purchase (1 point per dollar, representing 1.0% cash back)", None

    if card == ECO:
        if merchant in ECO_STANDARD:
            return Decimal("1"), "EcoCard named merchant exclusion: standard 1-point rate", None
        if merchant in GREEN_EV:
            return Decimal("5"), "EcoCard certified EV-charging partner: 5-point green rate", None
        explicit = txn.get("green_qualified")
        if explicit is True:
            return Decimal("5"), "EcoCard explicitly confirmed qualifying green purchase: 5-point rate", None
        if explicit is False:
            return Decimal("1"), "EcoCard explicitly not qualifying green purchase: standard 1-point rate", None
        if category == "green":
            return Decimal("5"), "EcoCard transaction classified Green: 5-point rate", None
        return Decimal("1"), "EcoCard other purchase: standard 1-point rate", None

    return None, None, "unsupported credit_card_type; this Skill only audits Business Bronze Rewards Card and EcoCard"


def audit_one(txn, subscriptions):
    required = ["credit_card_type", "merchant_name", "transaction_amount", "status", "rewards_earned"]
    missing = [key for key in required if key not in txn]
    identity = txn.get("transaction_id", txn.get("id", None))
    row = {"transaction_id": identity, "merchant_name": txn.get("merchant_name"), "credit_card_type": txn.get("credit_card_type")}
    if missing:
        row.update({"verdict": "needs_review", "reason": "missing required fields: " + ", ".join(missing)})
        return row
    try:
        amount = money(txn["transaction_amount"])
        actual = actual_points(txn["rewards_earned"])
    except ValueError as exc:
        row.update({"verdict": "needs_review", "reason": str(exc)})
        return row

    status = normalized(txn["status"])
    if status not in POSTED and status not in REVERSALS:
        row.update({"verdict": "needs_review", "reason": "transaction is not posted/completed or a recognized reversal", "actual_points": actual})
        return row

    rate, reason, uncertainty = rate_for_purchase(txn, subscriptions)
    if uncertainty:
        row.update({"verdict": "needs_review", "reason": uncertainty, "actual_points": actual})
        return row

    # Reversal records should remove the original award. If supplied as a positive
    # amount, make the expected points negative; signed negative amounts remain so.
    calc_amount = amount
    if status in REVERSALS and calc_amount > 0:
        calc_amount = -calc_amount
    expected = whole_points(calc_amount, rate)
    verdict = "match" if actual == expected else "discrepancy"
    row.update({
        "verdict": verdict,
        "actual_points": actual,
        "expected_points": expected,
        "point_delta_expected_minus_actual": expected - actual,
        "rate_points_per_dollar": str(rate),
        "reason": reason,
    })
    return row


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
            raise ValueError("input must be an object with a transactions array")
        supplied_subscriptions = payload.get("subscription_months_by_merchant", {})
        if not isinstance(supplied_subscriptions, dict):
            raise ValueError("subscription_months_by_merchant must be an object")
        subscriptions = {normalized(k): v for k, v in supplied_subscriptions.items()}
        rows = []
        for item in payload["transactions"]:
            if not isinstance(item, dict):
                rows.append({"verdict": "needs_review", "reason": "transaction entry must be an object"})
            else:
                rows.append(audit_one(item, subscriptions))
        discrepancies = [row for row in rows if row["verdict"] == "discrepancy"]
        review = [row for row in rows if row["verdict"] == "needs_review"]
        shortfall = sum(row["point_delta_expected_minus_actual"] for row in discrepancies)
        output = {
            "ok": True,
            "audited_transactions": rows,
            "discrepancies": discrepancies,
            "needs_review": review,
            "summary": {
                "input_transaction_count": len(payload["transactions"]),
                "matched_count": sum(row["verdict"] == "match" for row in rows),
                "discrepancy_count": len(discrepancies),
                "needs_review_count": len(review),
                "net_expected_minus_actual_points_for_discrepancies": shortfall,
                "total_customer_shortfall_points": max(shortfall, 0),
            },
        }
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        output = {"ok": False, "error": str(exc)}
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
