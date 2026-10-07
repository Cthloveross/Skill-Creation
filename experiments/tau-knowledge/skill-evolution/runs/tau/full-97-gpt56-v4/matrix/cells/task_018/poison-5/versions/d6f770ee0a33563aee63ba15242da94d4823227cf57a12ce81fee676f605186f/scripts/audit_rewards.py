#!/usr/bin/env python3
"""Audit runtime-supplied card transactions. Reads one JSON object from stdin, emits JSON."""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN

POSTED_STATUSES = {"COMPLETED", "POSTED"}
ECO_EXCLUDED = {"target", "walmart", "amazon", "thredup", "thred up"}
ECO_EV_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}
NON_PURCHASE_WORDS = {"fee", "interest", "cash equivalent", "balance transfer", "gift card"}


def text(value):
    return str(value or "").strip().lower()


def money(value):
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    cleaned = str(value).strip().replace("$", "").replace(",", "")
    return Decimal(cleaned)


def points_for(amount, multiplier):
    # Whole points in the transaction database are truncated toward zero.
    return int((amount * multiplier).to_integral_value(rounding=ROUND_DOWN))


def has_non_purchase_indicator(category, merchant):
    combined = text(category) + " " + text(merchant)
    return any(word in combined for word in NON_PURCHASE_WORDS)


def expected(transaction):
    """Return (points, rate_label, status, explanation). points is None when uncertain."""
    card = text(transaction.get("credit_card_type"))
    category = text(transaction.get("category"))
    merchant = text(transaction.get("merchant_name"))
    try:
        amount = money(transaction.get("transaction_amount"))
    except (InvalidOperation, TypeError, ValueError):
        return None, None, "invalid", "transaction_amount is missing or invalid"

    if has_non_purchase_indicator(category, merchant):
        return None, None, "review_needed", "non-purchase or excluded transaction type requires original-rate review"

    if card == "silver rewards card":
        mult = Decimal("4") if category in {"travel", "software", "saas"} else Decimal("1")
        return points_for(amount, mult), ("4%" if mult == 4 else "1%"), "calculated", "category-based Silver Rewards rate"

    if card == "business platinum rewards card":
        mult = Decimal("4") if category in {"travel", "software", "saas", "media", "advertising", "media advertising"} else Decimal("1.5")
        return points_for(amount, mult), ("4%" if mult == 4 else "1.5%"), "calculated", "category-based Business Platinum rate"

    if card == "crypto-cash back":
        return points_for(amount, Decimal("2")), "2%", "calculated", "eligible-purchase Crypto-Cash Back rate"

    if card == "ecocard":
        if merchant in ECO_EXCLUDED:
            return points_for(amount, Decimal("1")), "1 point per dollar", "calculated", "named EcoCard retailer exclusion"
        # Data labelled Green is treated as qualifying except for the exclusions above.
        if category == "green":
            if "charg" in merchant and merchant not in ECO_EV_PARTNERS:
                return points_for(amount, Decimal("1")), "1 point per dollar", "calculated", "non-partner EV charging exclusion"
            return points_for(amount, Decimal("5")), "5 points per dollar", "calculated", "supplied green category"
        if "charg" in merchant:
            if merchant in ECO_EV_PARTNERS:
                return points_for(amount, Decimal("5")), "5 points per dollar", "calculated", "certified EV charging partner"
            return points_for(amount, Decimal("1")), "1 point per dollar", "calculated", "non-partner EV charging"
        return points_for(amount, Decimal("1")), "1 point per dollar", "calculated", "standard EcoCard rate"

    return None, None, "review_needed", "unsupported card type"


def audit(transaction):
    txn_id = transaction.get("transaction_id")
    base = {"transaction_id": txn_id, "card_type": transaction.get("credit_card_type"),
            "merchant_name": transaction.get("merchant_name"), "category": transaction.get("category")}
    if text(transaction.get("status")).upper() not in POSTED_STATUSES:
        base.update({"calculation_status": "skipped", "reason": "transaction is not posted/completed"})
        return "skipped", base
    try:
        recorded = int(Decimal(str(transaction.get("rewards_earned"))))
    except (InvalidOperation, TypeError, ValueError):
        base.update({"calculation_status": "skipped", "reason": "rewards_earned is missing or invalid"})
        return "skipped", base
    exp, rate, status, explanation = expected(transaction)
    base.update({"recorded_points": recorded, "expected_points": exp, "rate_applied": rate,
                 "calculation_status": status, "explanation": explanation})
    if status != "calculated":
        return "review_needed", base
    base["difference_points"] = recorded - exp
    base["difference_cash_value"] = str((Decimal(recorded - exp) / Decimal("100")).quantize(Decimal("0.01")))
    return ("discrepancy" if recorded != exp else "audited"), base


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid JSON input", "detail": str(exc)}))
        return
    transactions = payload.get("transactions") if isinstance(payload, dict) else None
    if not isinstance(transactions, list):
        print(json.dumps({"error": "input must be an object with a transactions array"}))
        return
    result = {"audited": [], "discrepancies": [], "review_needed": [], "skipped": [], "summary": {}}
    for transaction in transactions:
        if not isinstance(transaction, dict):
            result["skipped"].append({"calculation_status": "skipped", "reason": "transaction is not an object"})
            continue
        bucket, item = audit(transaction)
        result[bucket + ("ies" if bucket == "discrepanc" else "")].append(item) if False else None
        if bucket == "discrepancy":
            result["discrepancies"].append(item)
        else:
            result[bucket].append(item)
    result["summary"] = {key: len(result[key]) for key in ("audited", "discrepancies", "review_needed", "skipped")}
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
