#!/usr/bin/env python3
"""Audit transaction reward points using documented, transaction-level rules.

Input: JSON object described in SKILL.md on stdin.
Output: JSON object with an audit result for every supplied transaction.
"""
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN

# Categories stated to be non-rewarding or not ordinary purchases for the
# programs for which the supplied rules explicitly identify them.
EXCLUDED_SILVER = {
    "gift card", "gift cards", "person-to-person", "person to person", "p2p",
    "fee", "fees", "interest", "insurance", "insurance premium",
}
EXCLUDED_BUSINESS = {
    "cash equivalent", "cash equivalents", "balance transfer", "balance transfers",
    "fee", "fees",
}
NON_ORDINARY = EXCLUDED_SILVER | EXCLUDED_BUSINESS
ECO_EXCLUDED_GREEN_MERCHANTS = {"target", "walmart", "amazon", "thredup"}
ECO_EV_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}
POSTED_STATUSES = {"completed", "posted"}


def norm(value):
    """Return a whitespace-normalized, case-folded string."""
    return " ".join(str(value or "").strip().casefold().split())


def parse_decimal(value):
    """Parse a numeric or conventional currency string without float rounding."""
    if isinstance(value, bool) or value is None:
        raise ValueError("amount is missing or not numeric")
    cleaned = str(value).strip().replace(",", "")
    cleaned = re.sub(r"[$]", "", cleaned)
    # Parenthesized amounts are credits and are not a standalone purchase.
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("amount is not a valid decimal") from exc


def parse_points(value):
    """Parse a stored whole-point value, rejecting fractional/ambiguous values."""
    if isinstance(value, bool) or value is None:
        raise ValueError("rewards_earned is missing")
    if isinstance(value, int):
        return value
    text = str(value).strip().casefold()
    match = re.fullmatch(r"(-?\d+)\s*(?:points?)?", text)
    if not match:
        raise ValueError("rewards_earned is not a whole-point value")
    return int(match.group(1))


def category_in(category, choices):
    value = norm(category)
    return value in choices


def has_nonordinary_marker(category):
    value = norm(category)
    return value in NON_ORDINARY


def rate_for(transaction, assume_ordinary):
    """Return (rate, reason, disposition) without inspecting stored reward points."""
    card = norm(transaction.get("credit_card_type"))
    category = norm(transaction.get("category"))
    merchant = norm(transaction.get("merchant_name"))

    if not card:
        return None, "Missing credit card type.", "manual_review"
    if not category:
        return None, "Missing merchant-coded category; enhanced eligibility cannot be verified.", "manual_review"

    if card == "silver rewards card":
        if category_in(category, EXCLUDED_SILVER):
            return None, "Category is explicitly excluded from Silver Rewards earning.", "not_audit_eligible"
        if category in {"travel", "software"}:
            return Decimal("4"), "Silver enhanced merchant category.", "calculable"
        return Decimal("1"), "Silver ordinary merchant category.", "calculable"

    if card == "business platinum rewards card":
        if category_in(category, EXCLUDED_BUSINESS):
            return None, "Category is explicitly excluded from Business Platinum earning.", "not_audit_eligible"
        if category in {"travel", "software", "media"}:
            return Decimal("4"), "Business Platinum enhanced merchant category.", "calculable"
        return Decimal("1.5"), "Business Platinum ordinary merchant category.", "calculable"

    if card == "crypto-cash back":
        if has_nonordinary_marker(category):
            return None, "Crypto eligibility is not established for a non-ordinary category.", "manual_review"
        if not assume_ordinary:
            return None, "Crypto eligibility was not supplied; its rate applies only to eligible purchases.", "manual_review"
        return Decimal("2"), "Crypto ordinary-purchase eligibility assumption.", "calculable"

    if card == "ecocard":
        if category == "green":
            if merchant in ECO_EXCLUDED_GREEN_MERCHANTS:
                return Decimal("1"), "EcoCard merchant is excluded from the Green rate.", "calculable"
            # For an EV charging category/merchant, do not infer green eligibility
            # unless the merchant is one of the three documented partner networks.
            if "charg" in merchant and merchant not in ECO_EV_PARTNERS:
                return Decimal("1"), "Non-partner EV charging does not receive the Green rate.", "calculable"
            return Decimal("5"), "EcoCard Green merchant category.", "calculable"
        return Decimal("1"), "EcoCard non-Green merchant category.", "calculable"

    return None, "No documented audit rule is available for this card type.", "manual_review"


def audit_one(transaction, assume_ordinary):
    result = {"transaction_id": transaction.get("transaction_id")}
    required = ("transaction_id", "credit_card_type", "merchant_name", "transaction_amount", "category", "status", "rewards_earned")
    missing = [key for key in required if transaction.get(key) in (None, "")]
    if missing:
        result.update({
            "outcome": "manual_review",
            "reason": "Missing required transaction fields: " + ", ".join(missing) + ".",
        })
        return result

    if norm(transaction.get("status")) not in POSTED_STATUSES:
        result.update({
            "outcome": "not_audit_eligible",
            "reason": "Rewards are audited after a transaction posts; status is not completed/posted.",
        })
        return result

    try:
        amount = parse_decimal(transaction["transaction_amount"])
    except ValueError as exc:
        result.update({"outcome": "manual_review", "reason": str(exc) + "."})
        return result
    if amount <= 0:
        result.update({
            "outcome": "not_audit_eligible",
            "reason": "A return, credit, or non-positive amount requires net-purchase/original-rate review.",
        })
        return result

    rate, rule_reason, disposition = rate_for(transaction, assume_ordinary)
    if disposition != "calculable":
        result.update({"outcome": disposition, "reason": rule_reason})
        return result

    try:
        recorded = parse_points(transaction["rewards_earned"])
    except ValueError as exc:
        result.update({"outcome": "manual_review", "reason": str(exc) + "."})
        return result

    expected = int((amount * rate).to_integral_value(rounding=ROUND_DOWN))
    result.update({
        "outcome": "match" if recorded == expected else "discrepancy",
        "recorded_points": recorded,
        "expected_points": expected,
        "points_per_dollar": format(rate, "f"),
        "reason": rule_reason + " Expected points are truncated down per transaction.",
    })
    return result


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        print(json.dumps({"status": "input_error", "error": "Input must be a JSON object: " + str(exc)}))
        return
    if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
        print(json.dumps({"status": "input_error", "error": "transactions must be an array in a JSON object."}))
        return

    assume_ordinary = payload.get("assume_ordinary_purchases", True)
    if not isinstance(assume_ordinary, bool):
        print(json.dumps({"status": "input_error", "error": "assume_ordinary_purchases must be boolean when supplied."}))
        return

    audits = []
    for item in payload["transactions"]:
        if not isinstance(item, dict):
            audits.append({"transaction_id": None, "outcome": "manual_review", "reason": "Transaction entry is not an object."})
        else:
            audits.append(audit_one(item, assume_ordinary))

    counts = {key: 0 for key in ("match", "discrepancy", "manual_review", "not_audit_eligible")}
    for item in audits:
        counts[item["outcome"]] += 1
    print(json.dumps({
        "status": "ok",
        "summary": {"transactions_received": len(audits), **counts},
        "audits": audits,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
