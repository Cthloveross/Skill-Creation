#!/usr/bin/env python3
"""Conservative transaction-level credit-card rewards comparison.

Reads a JSON object from stdin with {"transactions": [...]} and writes JSON to stdout.
It intentionally does not call banking tools and does not submit disputes.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

BONUS_SILVER = {"travel", "software"}
BONUS_BPLAT = {"travel", "software", "media"}
ECO_EXCLUDED_MERCHANTS = {"target", "walmart", "amazon"}
ECO_PARTNER_CHARGERS = {"tesla supercharger", "chargepoint", "evgo"}
SKIP_WORDS = {"pending", "reversed", "returned", "refunded", "refund", "cancelled", "canceled", "declined"}


def normal(value):
    return str(value or "").strip().casefold()


def money(value):
    text = str(value).strip().replace("$", "").replace(",", "")
    return Decimal(text)


def whole(value):
    # Recorded point amounts must be integral; reject rather than silently round.
    number = Decimal(str(value).strip().replace(",", ""))
    if number != number.to_integral_value():
        raise ValueError("rewards_earned must be a whole number")
    return int(number)


def floor_points(amount, rate):
    return int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))


def review_one(tx):
    required = ["transaction_id", "credit_card_type", "merchant_name", "transaction_amount", "category", "status", "rewards_earned"]
    absent = [field for field in required if field not in tx or tx[field] in (None, "")]
    if absent:
        raise ValueError("missing required field(s): " + ", ".join(absent))
    amount = money(tx["transaction_amount"])
    if amount < 0:
        raise ValueError("transaction_amount cannot be negative")
    recorded = whole(tx["rewards_earned"])
    card = normal(tx["credit_card_type"])
    category = normal(tx["category"])
    merchant = normal(tx["merchant_name"])
    status = normal(tx["status"])
    base = {
        "transaction_id": str(tx["transaction_id"]),
        "transaction_date": tx.get("transaction_date"),
        "card_type": tx["credit_card_type"],
        "merchant_name": tx["merchant_name"],
        "category": tx["category"],
        "amount": format(amount, "f"),
        "recorded_points": recorded,
        "expected_points": None,
        "difference_points": None,
        "difference_dollars": None,
    }
    if status != "completed" or any(word in status for word in SKIP_WORDS):
        base.update(review_status="skipped", rationale="Only completed posted purchases are reviewed.")
        return base

    rate = None
    certainty = "confirmed"
    rationale = ""
    if card == "silver rewards card":
        if category in BONUS_SILVER:
            rate = Decimal("0.04")
            rationale = "Travel and Software use the documented 4.0% rate."
        else:
            certainty = "indeterminate"
            rationale = "The supplied rules do not establish Silver Rewards' default rate for this category."
    elif card == "business platinum rewards card":
        if category in BONUS_BPLAT:
            rate = Decimal("0.04")
            rationale = "Travel, Software, and Media use the documented 4.0% rate."
        else:
            rate = Decimal("0.015")
            rationale = "Other eligible Business Platinum purchases use the documented 1.5% rate."
    elif card == "ecocard":
        qualification = normal(tx.get("green_qualification"))
        green_category = category in {"green", "sustainable"}
        excluded = merchant in ECO_EXCLUDED_MERCHANTS
        if qualification == "unknown":
            certainty = "indeterminate"
            rationale = "Green qualification is explicitly unknown and needs merchant/category confirmation."
        elif qualification == "excluded" or excluded:
            rate = Decimal("1")
            rationale = "This EcoCard purchase is subject to the standard 1 point per dollar rate."
        elif qualification == "qualified":
            rate = Decimal("5")
            rationale = "Green qualification is explicitly confirmed; the enhanced rate is 5 points per dollar."
        elif green_category:
            if "charging" in merchant and merchant not in ECO_PARTNER_CHARGERS:
                rate = Decimal("1")
                rationale = "Only named partner charging networks qualify for EcoCard's enhanced rate."
            else:
                rate = Decimal("5")
                rationale = "The submitted Green/Sustainable category is treated as qualifying absent a known exclusion."
        else:
            rate = Decimal("1")
            rationale = "Non-green EcoCard purchases use the standard 1 point per dollar rate."
    elif card == "crypto-cash back":
        eligible = tx.get("crypto_eligible")
        if eligible is True:
            rate = Decimal("0.02")
            rationale = "Eligibility is confirmed; Crypto-Cash Back earns 2.0% on eligible purchases."
        elif eligible is False:
            base.update(review_status="skipped", rationale="Transaction is identified as ineligible for Crypto-Cash Back rewards.")
            return base
        else:
            rate = Decimal("0.02")
            certainty = "potential"
            rationale = "2.0% is documented only for eligible Crypto-Cash Back purchases; eligibility is not confirmed."
    else:
        certainty = "indeterminate"
        rationale = "No supported earning rule is available for this card type."

    if rate is None:
        base.update(review_status="indeterminate", rationale=rationale)
        return base
    expected = floor_points(amount, rate)
    difference = expected - recorded
    base.update(
        expected_points=expected,
        difference_points=difference,
        difference_dollars=format(Decimal(difference) * Decimal("0.01"), ".2f"),
        rate=str(rate),
        rationale=rationale + " Fractional points are truncated per purchase.",
    )
    if difference == 0:
        base["review_status"] = "match"
    elif certainty == "potential":
        base["review_status"] = "potential_mismatch"
    else:
        base["review_status"] = "mismatch"
    return base


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        print(json.dumps({"results": [], "errors": ["invalid JSON input: " + str(exc)]}))
        return
    transactions = payload.get("transactions") if isinstance(payload, dict) else None
    if not isinstance(transactions, list):
        print(json.dumps({"results": [], "errors": ["transactions must be an array"]}))
        return
    results, errors = [], []
    for index, tx in enumerate(transactions):
        if not isinstance(tx, dict):
            errors.append({"index": index, "error": "transaction must be an object"})
            continue
        try:
            results.append(review_one(tx))
        except (ValueError, InvalidOperation) as exc:
            errors.append({"index": index, "transaction_id": tx.get("transaction_id"), "error": str(exc)})
    confirmed = [r for r in results if r["review_status"] == "mismatch"]
    potential = [r for r in results if r["review_status"] == "potential_mismatch"]
    output = {
        "results": results,
        "errors": errors,
        "summary": {
            "reviewed_records": len(results),
            "confirmed_mismatch_count": len(confirmed),
            "confirmed_difference_points": sum(r["difference_points"] for r in confirmed),
            "confirmed_difference_dollars": format(Decimal(sum(r["difference_points"] for r in confirmed)) * Decimal("0.01"), ".2f"),
            "potential_mismatch_count": len(potential),
            "potential_difference_points": sum(r["difference_points"] for r in potential),
            "potential_difference_dollars": format(Decimal(sum(r["difference_points"] for r in potential)) * Decimal("0.01"), ".2f"),
        },
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
