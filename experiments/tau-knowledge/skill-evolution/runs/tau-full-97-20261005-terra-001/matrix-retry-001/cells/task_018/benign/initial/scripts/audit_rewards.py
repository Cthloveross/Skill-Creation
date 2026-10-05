#!/usr/bin/env python3
"""Audit supported transaction rewards.

Input JSON:
  {"transactions": [transaction, ...]}
A transaction must contain transaction_id, credit_card_type, merchant_name,
transaction_amount, category, status, and rewards_earned.  An optional boolean
eligible may be set false for a known ineligible Crypto-Cash Back purchase.

Output JSON contains a summary and one result per submitted transaction.  This
program is intentionally read-only: it neither accesses banking systems nor
submits disputes.
"""
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

POSTED_STATUSES = {"COMPLETED", "POSTED"}
ECO_EXCLUDED_MERCHANTS = {"target", "walmart", "amazon", "thredup"}
ECO_EV_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}
BPLAT_BONUS_CATEGORIES = {"travel", "software", "media", "media advertising"}
SILVER_BONUS_CATEGORIES = {"travel", "software"}
BPLAT_INELIGIBLE_CATEGORIES = {
    "cash equivalent", "cash equivalents", "balance transfer", "balance transfers",
    "fee", "fees", "interest"
}


def normalized(value):
    return " ".join(str(value or "").strip().casefold().split())


def parse_amount(value):
    """Return a nonnegative Decimal monetary amount without float conversion."""
    if isinstance(value, bool):
        raise ValueError("transaction_amount must be a number or monetary string")
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        amount = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError("transaction_amount is not a valid monetary amount")
    if not amount.is_finite() or amount < 0:
        raise ValueError("transaction_amount must be a nonnegative finite amount")
    return amount


def parse_points(value):
    if isinstance(value, bool):
        raise ValueError("rewards_earned must be a whole number of points")
    if isinstance(value, int):
        points = value
    else:
        match = re.match(r"^\s*([+-]?\d+)\s*(?:points?)?\s*$", str(value), re.I)
        if not match:
            raise ValueError("rewards_earned must be a whole number of points")
        points = int(match.group(1))
    if points < 0:
        raise ValueError("rewards_earned must not be negative for a purchase audit")
    return points


def floor_points(amount, rate):
    return int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))


def rule_for(transaction, amount):
    """Return (points-per-dollar Decimal, explanatory basis) for a supported record."""
    card = str(transaction["credit_card_type"]).strip()
    category = normalized(transaction["category"])
    merchant = normalized(transaction["merchant_name"])

    if card == "Crypto-Cash Back":
        if transaction.get("eligible") is False:
            return Decimal("0"), "known ineligible purchase"
        return Decimal("2"), "Crypto-Cash Back eligible-purchase rate (2.0%)"

    if card == "Silver Rewards Card":
        if category in SILVER_BONUS_CATEGORIES:
            return Decimal("4"), "Silver Travel/Software enhanced rate (4.0%)"
        return Decimal("1"), "Silver standard rate outside Travel/Software (1.0%)"

    if card == "Business Platinum Rewards Card":
        if category in BPLAT_INELIGIBLE_CATEGORIES:
            return Decimal("0"), "Business Platinum excluded transaction type"
        if category in BPLAT_BONUS_CATEGORIES:
            return Decimal("4"), "Business Platinum Travel/Software/Media enhanced rate (4.0%)"
        return Decimal("1.5"), "Business Platinum standard rate (1.5%)"

    if card == "EcoCard":
        if merchant in ECO_EXCLUDED_MERCHANTS:
            return Decimal("1"), "EcoCard named-merchant exclusion (standard rate)"
        is_ev = "ev charging" in category or "charging" in category
        if is_ev and merchant not in ECO_EV_PARTNERS:
            return Decimal("1"), "EcoCard non-partner EV charging (standard rate)"
        if category == "green":
            return Decimal("5"), "EcoCard qualifying Green category rate (5 points per dollar)"
        return Decimal("1"), "EcoCard standard non-Green rate (1 point per dollar)"

    raise ValueError("unsupported credit_card_type")


def money_from_points(points):
    return format((Decimal(points) / Decimal("100")).quantize(Decimal("0.01")), ".2f")


def assess(transaction, index):
    result = {"input_index": index, "transaction_id": transaction.get("transaction_id")}
    required = [
        "transaction_id", "credit_card_type", "merchant_name", "transaction_amount",
        "category", "status", "rewards_earned"
    ]
    missing = [field for field in required if field not in transaction or transaction[field] in (None, "")]
    if missing:
        result.update(audit_status="invalid", reason="missing required fields: " + ", ".join(missing))
        return result
    if normalized(transaction["status"]).upper() not in POSTED_STATUSES:
        result.update(
            audit_status="manual_review",
            reason="only completed or posted purchase records can be calculated; returns, refunds, and pending records need review"
        )
        return result
    try:
        amount = parse_amount(transaction["transaction_amount"])
        recorded = parse_points(transaction["rewards_earned"])
        rate, basis = rule_for(transaction, amount)
        expected = floor_points(amount, rate)
    except ValueError as exc:
        result.update(audit_status="invalid", reason=str(exc))
        return result

    delta = expected - recorded
    result.update({
        "audit_status": "audited",
        "credit_card_type": transaction["credit_card_type"],
        "merchant_name": transaction["merchant_name"],
        "category": transaction["category"],
        "transaction_amount": format(amount, ".2f"),
        "recorded_points": recorded,
        "expected_points": expected,
        "delta_points": delta,
        "expected_redemption_value_usd": money_from_points(expected),
        "delta_redemption_value_usd": money_from_points(abs(delta)),
        "difference_direction": "undercredited" if delta > 0 else ("overcredited" if delta < 0 else "matches"),
        "points_per_dollar": format(rate, "f"),
        "basis": basis,
        "rounding": "fractional points are truncated (rounded down) per transaction"
    })
    return result


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid JSON input: " + str(exc)}))
        return
    if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
        print(json.dumps({"error": "input must be an object with a transactions array"}))
        return

    results = []
    for index, transaction in enumerate(payload["transactions"]):
        if not isinstance(transaction, dict):
            results.append({"input_index": index, "audit_status": "invalid", "reason": "transaction must be an object"})
        else:
            results.append(assess(transaction, index))

    audited = [r for r in results if r["audit_status"] == "audited"]
    output = {
        "summary": {
            "submitted": len(results),
            "audited": len(audited),
            "discrepancies": sum(r["delta_points"] != 0 for r in audited),
            "undercredited": sum(r["delta_points"] > 0 for r in audited),
            "overcredited": sum(r["delta_points"] < 0 for r in audited),
            "manual_review": sum(r["audit_status"] == "manual_review" for r in results),
            "invalid": sum(r["audit_status"] == "invalid" for r in results)
        },
        "results": results
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
