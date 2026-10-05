#!/usr/bin/env python3
"""Audit credit-card reward entries.

Input JSON:
{
  "transactions": [{
    "transaction_id": str, "credit_card_type": str,
    "merchant_name": str, "transaction_amount": number|string,
    "category": str, "status": str, "rewards_earned": number|string,
    "transaction_date": str (optional)
  }],
  "include_consistent": false (optional)
}

Output JSON contains likely point mismatches, optional consistent records, entries that
cannot safely be evaluated, and validation errors. Whole expected points are truncated.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN

CASH_EXCLUDED_CATEGORIES = {
    "cash equivalent", "cash equivalents", "balance transfer", "balance transfers",
    "fee", "fees", "interest",
}
ECO_EXCLUDED_MERCHANTS = {"target", "walmart", "amazon", "thredup"}
ECO_EV_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}


def text(value):
    return "" if value is None else str(value).strip()


def norm(value):
    return " ".join(text(value).casefold().split())


def decimal_value(value, field, errors, transaction_id):
    try:
        result = Decimal(text(value).replace("$", "").replace(",", ""))
    except (InvalidOperation, ValueError):
        errors.append({"transaction_id": transaction_id, "error": f"invalid {field}"})
        return None
    return result


def whole_points(amount, points_per_dollar):
    return int((amount * points_per_dollar).to_integral_value(rounding=ROUND_DOWN))


def rate_for(transaction):
    """Return (points_per_dollar, rationale) or (None, reason)."""
    card = norm(transaction.get("credit_card_type"))
    category = norm(transaction.get("category"))
    merchant = norm(transaction.get("merchant_name"))

    if category in CASH_EXCLUDED_CATEGORIES:
        return Decimal("0"), "documented non-reward-eligible transaction category"

    if card == "silver rewards card":
        if category in {"travel", "software"}:
            return Decimal("4"), "Silver enhanced travel/software rate"
        return Decimal("1"), "Silver standard rate"

    if card == "business platinum rewards card":
        if category in {"travel", "software", "media", "media advertising"}:
            return Decimal("4"), "Business Platinum enhanced category rate"
        return Decimal("1.5"), "Business Platinum standard rate"

    if card == "crypto-cash back":
        return Decimal("2"), "Crypto-Cash Back eligible-purchase rate"

    if card == "ecocard":
        if merchant in ECO_EXCLUDED_MERCHANTS:
            return Decimal("1"), "EcoCard expressly excluded merchant"
        if category == "green":
            # The runtime category is the available evidence of qualification.
            return Decimal("5"), "EcoCard Green-category rate"
        # Do not manufacture green eligibility from a merchant name alone.
        return Decimal("1"), "EcoCard standard non-Green rate"

    return None, "unsupported card type"


def money_string(points):
    value = (Decimal(points) / Decimal("100")).quantize(Decimal("0.01"))
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):.2f}"


def audit(transaction, errors):
    txid = text(transaction.get("transaction_id"))
    needed = ["transaction_id", "credit_card_type", "transaction_amount", "category", "status", "rewards_earned"]
    missing = [field for field in needed if not text(transaction.get(field))]
    if missing:
        errors.append({"transaction_id": txid or None, "error": "missing required fields: " + ", ".join(missing)})
        return None, None

    status = norm(transaction.get("status"))
    amount = decimal_value(transaction.get("transaction_amount"), "transaction_amount", errors, txid)
    actual_decimal = decimal_value(transaction.get("rewards_earned"), "rewards_earned", errors, txid)
    if amount is None or actual_decimal is None:
        return None, None
    if actual_decimal != actual_decimal.to_integral_value():
        errors.append({"transaction_id": txid, "error": "rewards_earned must be whole points"})
        return None, None
    if status != "completed" or amount <= 0:
        return None, {"transaction_id": txid, "reason": "not a completed positive purchase"}

    rate, rationale = rate_for(transaction)
    if rate is None:
        return None, {"transaction_id": txid, "reason": rationale}

    expected = whole_points(amount, rate)
    actual = int(actual_decimal)
    difference = expected - actual
    record = {
        "transaction_id": txid,
        "transaction_date": text(transaction.get("transaction_date")) or None,
        "merchant_name": text(transaction.get("merchant_name")) or None,
        "card_type": text(transaction.get("credit_card_type")),
        "category": text(transaction.get("category")),
        "amount": f"{amount:.2f}",
        "recorded_points": actual,
        "expected_points": expected,
        "point_difference": difference,
        "cash_equivalent_difference": money_string(difference),
        "rationale": rationale,
    }
    if difference:
        record["determination"] = "likely_mismatch"
        record["direction"] = "under_credit" if difference > 0 else "over_credit"
    else:
        record["determination"] = "matches_documented_rate"
    return record, None


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "input must be valid JSON", "detail": str(exc)}))
        return

    transactions = payload.get("transactions") if isinstance(payload, dict) else None
    if not isinstance(transactions, list):
        print(json.dumps({"error": "transactions must be an array"}))
        return

    errors, findings, consistent, unreviewable = [], [], [], []
    for item in transactions:
        if not isinstance(item, dict):
            errors.append({"transaction_id": None, "error": "each transaction must be an object"})
            continue
        record, skipped = audit(item, errors)
        if skipped:
            unreviewable.append(skipped)
        elif record:
            (findings if record["determination"] == "likely_mismatch" else consistent).append(record)

    output = {
        "reviewed_count": len(findings) + len(consistent),
        "likely_mismatch_count": len(findings),
        "findings": findings,
        "unreviewable": unreviewable,
        "validation_errors": errors,
    }
    if bool(payload.get("include_consistent", False)):
        output["consistent"] = consistent
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
