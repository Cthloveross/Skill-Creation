#!/usr/bin/env python3
"""Audit posted rewards transactions.

Read one JSON object from stdin with a `transactions` list and emit a JSON report.
The script is calculation-only and never invokes banking tools or changes account data.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

BUSINESS = "business bronze rewards card"
ECO = "ecocard"
BUSINESS_ZERO = {
    "wework", "regus", "industrious", "gusto", "adp", "paychex", "rippling",
}
SAAS = {"slack", "zoom", "hubspot", "salesforce"}
ECO_STANDARD = {"target", "walmart", "amazon", "thredup"}
EV_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}
POSTED = {"completed", "posted"}


def norm(value):
    return " ".join(str(value or "").casefold().split())


def points_for(amount, rate):
    """Return floor(amount * rate) as an integer using decimal arithmetic."""
    return int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))


def money(points):
    return format((Decimal(points) / Decimal("100")).quantize(Decimal("0.01")), "f")


def base_item(tx, index):
    return {
        "index": index,
        "transaction_id": tx.get("transaction_id"),
        "transaction_date": tx.get("transaction_date"),
        "card_type": tx.get("credit_card_type"),
        "merchant_name": tx.get("merchant_name"),
        "amount": tx.get("transaction_amount"),
        "recorded_points": tx.get("rewards_earned"),
    }


def review(item, reason):
    item.update({"result": "needs_review", "reason": reason, "expected_points": None,
                 "point_difference": None, "cash_value_difference_usd": None})
    return item


def audit_one(tx, index):
    if not isinstance(tx, dict):
        return review({"index": index}, "Transaction must be a JSON object.")
    item = base_item(tx, index)
    card = norm(tx.get("credit_card_type"))
    if card not in {BUSINESS, ECO}:
        return review(item, "Unsupported card type; only Business Bronze Rewards Card and EcoCard are covered.")
    if norm(tx.get("status")) not in POSTED:
        return review(item, "Only posted or completed purchase transactions can be audited with this formula.")
    try:
        amount = Decimal(str(tx.get("transaction_amount")))
    except (InvalidOperation, ValueError):
        return review(item, "Transaction amount is missing or not a valid decimal.")
    if not amount.is_finite() or amount < 0:
        return review(item, "Negative, return, reversal, or non-finite amounts require the original transaction relationship.")
    try:
        recorded = int(tx.get("rewards_earned"))
    except (TypeError, ValueError):
        return review(item, "Recorded rewards must be an integer point value.")
    if recorded < 0:
        return review(item, "Negative recorded rewards require return/reversal review.")

    merchant = norm(tx.get("merchant_name"))
    if not merchant:
        return review(item, "Merchant name is required to apply merchant-specific rules.")

    if card == BUSINESS:
        if merchant in BUSINESS_ZERO:
            expected, rule = 0, "Business Bronze named merchant exclusion (0 points)."
        elif merchant in SAAS:
            tenure = tx.get("saas_after_first_12_months")
            if tenure is None:
                return review(item, "SaaS subscription tenure is required: these merchants earn 0 only after month 12.")
            if not isinstance(tenure, bool):
                return review(item, "saas_after_first_12_months must be true or false.")
            expected = 0 if tenure else points_for(amount, Decimal("1"))
            rule = ("Business Bronze SaaS after first 12 months (0 points)." if tenure
                    else "Business Bronze SaaS within first 12 months (1 point per dollar).")
        else:
            expected, rule = points_for(amount, Decimal("1")), "Business Bronze eligible purchase (1 point per dollar)."
    else:
        if merchant in ECO_STANDARD:
            expected, rule = points_for(amount, Decimal("1")), "EcoCard named standard-rate exclusion (1 point per dollar)."
        else:
            is_ev = tx.get("is_ev_charging") is True
            green_flag = tx.get("qualifies_green")
            if green_flag is not None and not isinstance(green_flag, bool):
                return review(item, "qualifies_green must be true or false when supplied.")
            if is_ev:
                qualifies = merchant in EV_PARTNERS
                rule = ("EcoCard certified EV charging partner (5 points per dollar)." if qualifies
                        else "EcoCard nonpartner EV charging (1 point per dollar).")
            elif green_flag is not None:
                qualifies = green_flag
                rule = ("EcoCard confirmed qualifying green purchase (5 points per dollar)." if qualifies
                        else "EcoCard confirmed non-green purchase (1 point per dollar).")
            else:
                qualifies = norm(tx.get("category")) == "green"
                rule = ("EcoCard Green category treated as qualifying; confirm merchant recognition if disputed (5 points per dollar)."
                        if qualifies else "EcoCard non-green/default purchase (1 point per dollar).")
            expected = points_for(amount, Decimal("5") if qualifies else Decimal("1"))

    difference = expected - recorded
    item.update({
        "result": "match" if difference == 0 else "mismatch",
        "rule_applied": rule,
        "expected_points": expected,
        "recorded_points": recorded,
        "point_difference": difference,
        "cash_value_difference_usd": money(difference),
    })
    return item


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "Invalid JSON input: " + str(exc)}))
        return
    transactions = payload.get("transactions") if isinstance(payload, dict) else None
    if not isinstance(transactions, list):
        print(json.dumps({"error": "Input must be an object containing a transactions array."}))
        return
    items = [audit_one(tx, i) for i, tx in enumerate(transactions)]
    mismatches = [x for x in items if x.get("result") == "mismatch"]
    reviews = [x for x in items if x.get("result") == "needs_review"]
    point_difference = sum(x["point_difference"] for x in mismatches)
    report = {
        "items": items,
        "mismatches": mismatches,
        "needs_review": reviews,
        "summary": {
            "transactions_received": len(items),
            "matches": sum(x.get("result") == "match" for x in items),
            "mismatches": len(mismatches),
            "needs_review": len(reviews),
            "net_mismatch_point_difference": point_difference,
            "net_mismatch_cash_value_difference_usd": money(point_difference),
            "difference_interpretation": "Positive means recorded points are below calculated expected points; negative means recorded points exceed calculated expected points.",
        },
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
