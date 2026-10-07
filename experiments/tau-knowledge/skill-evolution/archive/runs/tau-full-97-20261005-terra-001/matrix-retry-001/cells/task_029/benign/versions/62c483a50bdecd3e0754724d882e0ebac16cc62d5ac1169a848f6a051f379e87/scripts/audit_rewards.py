#!/usr/bin/env python3
"""Audit documented credit-card reward rules.

Reads one JSON object from stdin and emits one JSON object to stdout.  It uses
only Python's standard library and does not access banking systems.
"""
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN

BONUS_CATEGORIES = {
    "Business Platinum Rewards Card": {"travel": Decimal("4"), "software": Decimal("4"), "media": Decimal("4")},
    "Silver Rewards Card": {"travel": Decimal("4"), "software": Decimal("4")},
}
DEFAULT_RATES = {
    "Business Platinum Rewards Card": Decimal("1.5"),
    "Silver Rewards Card": Decimal("1"),
    "Crypto-Cash Back": Decimal("2"),
}
KNOWN_CARDS = set(DEFAULT_RATES) | {"EcoCard"}
ECO_EXCLUDED_MERCHANTS = {"target", "walmart", "amazon", "thredup"}
ECO_EV_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}
NON_PURCHASE_TERMS = {
    "fee", "fees", "interest", "cash equivalent", "cash advance",
    "balance transfer", "gift card", "person-to-person", "p2p",
}
RETURN_TERMS = {"returned", "refunded", "refund", "reversed", "credit", "chargeback"}
POSTED_STATUSES = {"completed", "posted"}


def norm(value):
    return " ".join(str(value or "").strip().casefold().split())


def parse_amount(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("transaction_amount is required")
    text = str(value).strip().replace(",", "")
    text = re.sub(r"^\$", "", text)
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("transaction_amount must be a decimal amount") from exc
    if amount < 0:
        raise ValueError("transaction_amount must not be negative for a purchase record")
    return amount


def parse_points(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("rewards_earned is required")
    try:
        points = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError("rewards_earned must be a whole-point number") from exc
    if points < 0 or points != points.to_integral_value():
        raise ValueError("rewards_earned must be a non-negative whole number")
    return int(points)


def contains_any(text, terms):
    return any(term in text for term in terms)


def eco_rate(txn, category, merchant):
    """Return (rate, assumption), or (None, reason) for an ambiguous Eco case."""
    if merchant in ECO_EXCLUDED_MERCHANTS:
        return Decimal("1"), "EcoCard merchant exclusion: standard rate"
    if "charg" in merchant or "ev charging" in category:
        if merchant in ECO_EV_PARTNERS:
            return Decimal("5"), "certified EV charging partner"
        return None, "EV charging is enhanced only at a certified partner; partner cannot be confirmed"
    confirmed = txn.get("green_merchant_confirmed")
    if confirmed is True:
        return Decimal("5"), "green eligibility explicitly confirmed"
    if confirmed is False:
        return Decimal("1"), "green eligibility explicitly not confirmed"
    if category in {"green", "sustainable"}:
        return Decimal("5"), "assumed qualifying from recorded Green/Sustainable category"
    return Decimal("1"), "standard EcoCard rate"


def make_base(txn, amount, actual):
    return {
        "transaction_id": str(txn.get("transaction_id", "")),
        "transaction_date": txn.get("transaction_date"),
        "card_type": txn.get("credit_card_type"),
        "merchant_name": txn.get("merchant_name"),
        "category": txn.get("category"),
        "amount": format(amount, ".2f"),
        "actual_points": actual,
        "actual_cash_equivalent": format(Decimal(actual) / Decimal("100"), ".2f"),
    }


def assess(txn):
    required = ("transaction_id", "credit_card_type", "merchant_name", "category", "status")
    absent = [key for key in required if not str(txn.get(key, "")).strip()]
    if absent:
        raise ValueError("missing required field(s): " + ", ".join(absent))
    amount = parse_amount(txn.get("transaction_amount"))
    actual = parse_points(txn.get("rewards_earned"))
    item = make_base(txn, amount, actual)
    card = str(txn["credit_card_type"]).strip()
    category = norm(txn["category"])
    merchant = norm(txn["merchant_name"])
    status = norm(txn["status"])

    if card not in KNOWN_CARDS:
        item["reason"] = "Unsupported card type; no documented rate is available to this Skill"
        return "needs_review", item
    if contains_any(status, RETURN_TERMS):
        item["reason"] = "Return/refund/credit records require net-purchase linkage and are not assessed as a new purchase"
        return "excluded_or_non_purchase", item
    if status not in POSTED_STATUSES:
        item["reason"] = "Transaction is not posted/completed, so final rewards cannot yet be assessed"
        return "needs_review", item
    if contains_any(category + " " + merchant, NON_PURCHASE_TERMS):
        item["expected_points"] = 0
        item["expected_cash_equivalent"] = "0.00"
        item["reason"] = "Non-purchase or excluded transaction type does not earn ordinary purchase rewards"
        return "excluded_or_non_purchase", item

    if card == "EcoCard":
        rate, reason = eco_rate(txn, category, merchant)
        if rate is None:
            item["reason"] = reason
            return "needs_review", item
    elif card in BONUS_CATEGORIES and category in BONUS_CATEGORIES[card]:
        rate = BONUS_CATEGORIES[card][category]
        reason = "documented bonus-category rate"
    else:
        rate = DEFAULT_RATES[card]
        reason = "documented default purchase rate"

    expected = int((amount * rate).to_integral_value(rounding=ROUND_DOWN))
    delta = actual - expected
    item.update({
        "rate_points_per_dollar": format(rate, "f"),
        "rate_percent": format(rate, "f"),
        "expected_points": expected,
        "expected_cash_equivalent": format(Decimal(expected) / Decimal("100"), ".2f"),
        "delta_points": delta,
        "delta_cash_equivalent": format(Decimal(delta) / Decimal("100"), ".2f"),
        "assessment_basis": reason,
    })
    return ("correct" if delta == 0 else "discrepancies"), item


def main():
    result = {
        "summary": {"assessed": 0, "correct": 0, "discrepancies": 0, "needs_review": 0, "excluded_or_non_purchase": 0},
        "discrepancies": [], "correct": [], "needs_review": [],
        "excluded_or_non_purchase": [], "errors": [],
    }
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        result["errors"].append("Input is not valid JSON: " + str(exc))
        print(json.dumps(result, sort_keys=True))
        return
    transactions = data.get("transactions") if isinstance(data, dict) else None
    if not isinstance(transactions, list):
        result["errors"].append("Input must be an object containing a transactions array")
        print(json.dumps(result, sort_keys=True))
        return

    for index, txn in enumerate(transactions):
        if not isinstance(txn, dict):
            result["errors"].append("transactions[%d] must be an object" % index)
            continue
        try:
            bucket, item = assess(txn)
        except ValueError as exc:
            result["errors"].append("transactions[%d]: %s" % (index, exc))
            continue
        result[bucket].append(item)
        result["summary"][bucket] += 1
        if bucket in {"correct", "discrepancies"}:
            result["summary"]["assessed"] += 1
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
