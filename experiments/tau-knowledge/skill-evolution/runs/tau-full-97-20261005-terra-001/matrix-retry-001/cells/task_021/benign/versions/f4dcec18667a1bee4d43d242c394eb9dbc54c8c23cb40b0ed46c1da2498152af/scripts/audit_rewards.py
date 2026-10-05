#!/usr/bin/env python3
"""Audit documented rewards rules. Reads one JSON object from stdin and writes one JSON object."""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

BRONZE = "Business Bronze Rewards Card"
ECO = "EcoCard"
BRONZE_ZERO = {"wework", "regus", "industrious", "gusto", "adp", "paychex", "rippling"}
BRONZE_SAAS = {"slack", "zoom", "hubspot", "salesforce"}
ECO_STANDARD = {"target", "walmart", "amazon", "thredup"}
ECO_EV_GREEN = {"tesla supercharger", "chargepoint", "evgo"}
POSTED = {"completed", "posted"}


def norm(value):
    return " ".join(str(value or "").strip().casefold().split())


def whole_points(value):
    if isinstance(value, bool):
        raise ValueError("boolean is not a points value")
    if isinstance(value, int):
        return value
    text = str(value).strip().casefold()
    if text.endswith("points"):
        text = text[:-6].strip()
    if text.startswith("+"):
        text = text[1:]
    if not text or any(c not in "0123456789" for c in text):
        raise ValueError("rewards_earned must be a whole-number points value")
    return int(text)


def money(value):
    if isinstance(value, bool):
        raise ValueError("boolean is not an amount")
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("transaction_amount is invalid") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("transaction_amount must be a nonnegative finite value")
    return amount


def floor_decimal(value):
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def review(tx, reason):
    return {"transaction_id": tx.get("transaction_id"), "reason": reason}


def audit_one(tx, options):
    required = ("transaction_id", "credit_card_type", "merchant_name", "transaction_amount", "status", "rewards_earned")
    missing = [key for key in required if tx.get(key) in (None, "")]
    if missing:
        return None, review(tx, "missing required field(s): " + ", ".join(missing))
    if norm(tx["status"]) not in POSTED:
        return None, review(tx, "transaction is not a posted/completed positive purchase")
    try:
        amount = money(tx["transaction_amount"])
        displayed = whole_points(tx["rewards_earned"])
    except ValueError as exc:
        return None, review(tx, str(exc))
    if amount == 0:
        return None, review(tx, "zero-value transaction requires transaction-type review")

    card = str(tx["credit_card_type"]).strip()
    merchant = norm(tx["merchant_name"])
    if card == BRONZE:
        if merchant in BRONZE_ZERO:
            expected, basis = 0, "Business Bronze named merchant exclusion: 0%"
        elif merchant in BRONZE_SAAS:
            if tx.get("beyond_initial_12_months") is True:
                expected, basis = 0, "Business Bronze SaaS payment after initial 12 months: 0%"
            elif tx.get("beyond_initial_12_months") is False:
                expected = floor_decimal(amount)
                basis = "Business Bronze eligible 1.0% cash back stored as points; floor(amount × 1)"
            else:
                return None, review(tx, "named SaaS merchant needs subscription-tenure confirmation")
        else:
            expected = floor_decimal(amount)
            basis = "Business Bronze eligible 1.0% cash back stored as points; floor(amount × 1)"
    elif card == ECO:
        known_green = {norm(x) for x in options.get("known_green_merchants", [])}
        if merchant in ECO_STANDARD:
            green, basis = False, "EcoCard named standard-rate merchant exclusion"
        elif merchant in ECO_EV_GREEN:
            green, basis = True, "EcoCard certified EV charging network"
        elif isinstance(tx.get("green_qualified"), bool):
            green = tx["green_qualified"]
            basis = "EcoCard supplied green-qualification indicator"
        elif options.get("green_category_is_qualified", True) and norm(tx.get("category")) == "green":
            green, basis = True, "EcoCard validated Green transaction category"
        elif merchant in known_green:
            green, basis = True, "EcoCard supplied certified green merchant list"
        else:
            green, basis = False, "EcoCard non-green/standard transaction classification"
        multiplier = Decimal(5 if green else 1)
        expected = floor_decimal(amount * multiplier)
        basis += "; floor(amount × %d points per dollar)" % int(multiplier)
    else:
        return None, review(tx, "unsupported card type: " + card)

    entry = {
        "transaction_id": str(tx["transaction_id"]),
        "card_type": card,
        "merchant_name": str(tx["merchant_name"]),
        "displayed_rewards_points": displayed,
        "expected_rewards_points": expected,
        "new_rewards_earned": str(expected) + " points",
        "delta_points": expected - displayed,
        "basis": basis,
    }
    return entry, None


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"error": "invalid JSON input: " + str(exc)}))
        return
    if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
        print(json.dumps({"error": "input must be an object containing a transactions array"}))
        return
    options = payload.get("options", {})
    if not isinstance(options, dict):
        options = {}
    audited, discrepancies, needs_review, input_errors = [], [], [], []
    grouped = {}
    for index, tx in enumerate(payload["transactions"]):
        if not isinstance(tx, dict):
            input_errors.append({"index": index, "reason": "transaction must be an object"})
            continue
        entry, skipped = audit_one(tx, options)
        if skipped:
            needs_review.append(skipped)
            continue
        audited.append(entry)
        group = grouped.setdefault(entry["card_type"], {"audited_count": 0, "discrepancy_count": 0, "total_delta_points": 0})
        group["audited_count"] += 1
        if entry["delta_points"] != 0:
            discrepancies.append(entry)
            group["discrepancy_count"] += 1
            group["total_delta_points"] += entry["delta_points"]
    output = {
        "audited": audited,
        "discrepancies": discrepancies,
        "needs_review": needs_review,
        "input_errors": input_errors,
        "summary": {
            "input_transaction_count": len(payload["transactions"]),
            "audited_count": len(audited),
            "discrepancy_count": len(discrepancies),
            "needs_review_count": len(needs_review),
            "by_card_type": grouped,
        },
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
