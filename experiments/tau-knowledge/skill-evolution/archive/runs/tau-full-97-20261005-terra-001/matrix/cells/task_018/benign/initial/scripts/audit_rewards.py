#!/usr/bin/env python3
"""Audit credit-card reward records. Read JSON stdin and write JSON stdout."""
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN

CENTS_PER_POINT = Decimal("0.01")
STANDARD_EXCLUDED_MERCHANTS = {"target", "walmart", "amazon", "thredup", "thred up"}
EV_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}


def norm(value):
    return " ".join(str(value or "").strip().casefold().split())


def money(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("missing amount")
    cleaned = re.sub(r"[^0-9.\-]", "", str(value).replace(",", ""))
    if not cleaned or cleaned in {"-", ".", "-."}:
        raise ValueError("invalid amount")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("invalid amount") from exc


def whole_points(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("missing rewards_earned")
    cleaned = re.sub(r"[^0-9.\-]", "", str(value).replace(",", ""))
    try:
        number = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("invalid rewards_earned") from exc
    if number != number.to_integral_value():
        raise ValueError("rewards_earned must be whole points")
    return int(number)


def get_field(txn, *names):
    for name in names:
        if name in txn and txn[name] not in (None, ""):
            return txn[name]
    return None


def excluded_status(status, category):
    text = norm(status) + " " + norm(category)
    markers = ("return", "refund", "credit", "reversal", "fee", "interest", "balance transfer", "cash equivalent")
    return any(marker in text for marker in markers)


def rate_for(card, category, merchant):
    card_n = norm(card)
    category_n = norm(category)
    merchant_n = norm(merchant)
    if card_n == "crypto-cash back":
        return Decimal("0.02"), "Crypto-Cash Back eligible-purchase rate"
    if card_n == "silver rewards card":
        if category_n in {"travel", "software", "saas", "software/saas"}:
            return Decimal("0.04"), "Silver enhanced merchant category"
        return Decimal("0.01"), "Silver standard merchant category"
    if card_n == "business platinum rewards card":
        if category_n in {"travel", "software", "saas", "software/saas", "media", "media advertising", "advertising", "digital advertising"}:
            return Decimal("0.04"), "Business Platinum enhanced merchant category"
        return Decimal("0.015"), "Business Platinum standard merchant category"
    if card_n == "ecocard":
        ev_category = category_n in {"ev charging", "electric vehicle charging", "ev_charging"}
        if merchant_n in STANDARD_EXCLUDED_MERCHANTS:
            return Decimal("0.01"), "EcoCard named merchant exclusion"
        if ev_category:
            if merchant_n in EV_PARTNERS:
                return Decimal("0.05"), "EcoCard certified EV-charging partner"
            return Decimal("0.01"), "EcoCard non-partner EV charging"
        if category_n == "green":
            return Decimal("0.05"), "EcoCard supplied qualifying-green category"
        return Decimal("0.01"), "EcoCard standard/non-green category"
    return None, "unsupported card type"


def expected_points(amount, rate):
    # Dollar amount times percentage produces cash back; dividing by $0.01 gives points.
    raw = (amount * rate) / CENTS_PER_POINT
    return int(raw.to_integral_value(rounding=ROUND_DOWN))


def cash_string(points):
    return format((Decimal(points) * CENTS_PER_POINT).quantize(Decimal("0.01")), "f")


def audit(transaction, tolerance):
    if not isinstance(transaction, dict):
        return None, {"transaction": transaction, "reason": "transaction is not an object"}
    txn_id = get_field(transaction, "transaction_id", "id")
    card = get_field(transaction, "credit_card_type", "card_type")
    merchant = get_field(transaction, "merchant_name", "merchant")
    category = get_field(transaction, "category")
    status = get_field(transaction, "status")
    if not txn_id or not card:
        return None, {"transaction_id": txn_id, "reason": "missing transaction_id or card type"}
    if norm(status) not in {"completed", "posted", "settled"}:
        return None, {"transaction_id": txn_id, "reason": "transaction is not a completed/posted purchase"}
    if excluded_status(status, category):
        return None, {"transaction_id": txn_id, "reason": "return, credit, fee, cash-equivalent, or similar excluded record"}
    try:
        amount = money(get_field(transaction, "transaction_amount", "amount"))
        actual = whole_points(get_field(transaction, "rewards_earned", "rewards_points"))
    except ValueError as exc:
        return None, {"transaction_id": txn_id, "reason": str(exc)}
    rate, basis = rate_for(card, category, merchant)
    if rate is None:
        return None, {"transaction_id": txn_id, "reason": basis, "card_type": card}
    expected = expected_points(amount, rate)
    difference = expected - actual
    if difference == 0:
        classification = "match"
    elif abs(difference) <= tolerance:
        classification = "rounding_review"
    else:
        classification = "discrepancy"
    finding = {
        "transaction_id": str(txn_id),
        "card_type": str(card),
        "merchant_name": str(merchant or ""),
        "category": str(category or ""),
        "transaction_date": get_field(transaction, "transaction_date", "date"),
        "amount": format(amount.quantize(Decimal("0.01")), "f"),
        "rate_percent": format(rate * Decimal("100"), "f"),
        "eligibility_basis": basis,
        "expected_points": expected,
        "expected_cash_back": cash_string(expected),
        "actual_points": actual,
        "actual_cash_back": cash_string(actual),
        "difference_points": difference,
        "difference_cash_back": cash_string(difference),
        "classification": classification,
    }
    return finding, None


def main():
    try:
        payload = json.load(sys.stdin)
        transactions = payload.get("transactions")
        if not isinstance(transactions, list):
            raise ValueError("transactions must be an array")
        tolerance = int(payload.get("rounding_tolerance_points", 0))
        if tolerance < 0:
            raise ValueError("rounding_tolerance_points must be nonnegative")
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}))
        return

    findings, skipped, disputes = [], [], []
    for transaction in transactions:
        finding, skipped_item = audit(transaction, tolerance)
        if skipped_item is not None:
            skipped.append(skipped_item)
            continue
        findings.append(finding)
        if finding["classification"] == "discrepancy":
            disputes.append({
                "transaction_id": finding["transaction_id"],
                "card_type": finding["card_type"],
                "merchant_name": finding["merchant_name"],
                "difference_points": finding["difference_points"],
                "difference_cash_back": finding["difference_cash_back"],
                "direction": "under_earned" if finding["difference_points"] > 0 else "over_earned",
            })
    expected_total = sum(item["expected_points"] for item in findings)
    actual_total = sum(item["actual_points"] for item in findings)
    output = {
        "summary": {
            "transactions_received": len(transactions),
            "transactions_audited": len(findings),
            "transactions_skipped": len(skipped),
            "discrepancies": len(disputes),
            "rounding_reviews": sum(item["classification"] == "rounding_review" for item in findings),
            "expected_points_total": expected_total,
            "actual_points_total": actual_total,
            "difference_points_total": expected_total - actual_total,
            "difference_cash_back_total": cash_string(expected_total - actual_total),
        },
        "findings": findings,
        "disputes": disputes,
        "skipped": skipped,
        "assumptions": [
            "Completed/posted records without an explicit exclusion marker are treated as eligible purchases.",
            "Merchant category is taken from the supplied category field.",
            "Expected fractional points are truncated toward zero because recorded rewards are whole points.",
            "EcoCard uses an enhanced rate only where a supplied Green category or a named EV partner supports it."
        ]
    }
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
