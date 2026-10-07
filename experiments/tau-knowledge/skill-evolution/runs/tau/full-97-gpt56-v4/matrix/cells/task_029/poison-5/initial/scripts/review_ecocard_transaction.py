#!/usr/bin/env python3
"""Deterministically review one completed EcoCard rewards transaction.

Reads a JSON object from stdin and emits a JSON object to stdout. It does not
call banking tools, mutate data, or submit a dispute.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

EXCLUDED_MERCHANTS = {"target", "walmart", "amazon"}
QUALIFYING_EV_NETWORKS = {"tesla supercharger", "chargepoint", "evgo"}


def as_text(value):
    return "" if value is None else str(value).strip()


def normalized(value):
    return " ".join(as_text(value).casefold().split())


def output_error(message):
    return {"error": message}


def is_ev_charging(merchant, category):
    text = normalized(merchant) + " " + normalized(category)
    return "charging" in text or "ev " in text or text.startswith("ev")


def matching_ev_network(merchant):
    name = normalized(merchant)
    return any(network in name for network in QUALIFYING_EV_NETWORKS)


def review(payload):
    required = ["transaction_amount", "recorded_points", "merchant_name", "category", "card_type", "status"]
    missing = [field for field in required if field not in payload]
    if missing:
        return output_error("Missing required field(s): " + ", ".join(missing))
    if normalized(payload["card_type"]) != "ecocard":
        return output_error("This Skill only evaluates EcoCard transactions.")
    if normalized(payload["status"]) != "completed":
        return output_error("Only completed transactions can be evaluated.")
    try:
        amount = Decimal(str(payload["transaction_amount"]))
    except (InvalidOperation, ValueError):
        return output_error("transaction_amount must be a valid decimal amount.")
    if not amount.is_finite() or amount < 0:
        return output_error("transaction_amount must be a nonnegative finite amount.")
    try:
        recorded = int(payload["recorded_points"])
    except (ValueError, TypeError):
        return output_error("recorded_points must be a whole number.")
    if recorded < 0:
        return output_error("recorded_points must be nonnegative.")

    merchant = normalized(payload["merchant_name"])
    category = normalized(payload["category"])
    authorized_category = payload.get("green_category_authorized") is True
    partner_eligible = payload.get("partner_eligible")
    if partner_eligible not in (True, False, None):
        return output_error("partner_eligible must be true, false, or null.")

    if merchant in EXCLUDED_MERCHANTS:
        eligibility = "standard"
        reason = "The merchant is an explicit EcoCard green-rate exclusion."
    elif is_ev_charging(merchant, category):
        if matching_ev_network(merchant):
            eligibility = "green"
            reason = "The EV charging merchant is a qualifying certified charging network."
        else:
            eligibility = "standard"
            reason = "EV charging is green-rate eligible only at supported certified charging networks."
    elif partner_eligible is True:
        eligibility = "green"
        reason = "Verified merchant, receipt, or seller-of-record evidence supports green eligibility."
    elif partner_eligible is False:
        eligibility = "standard"
        reason = "Available merchant eligibility evidence does not support the green rate."
    elif category == "green" and authorized_category:
        eligibility = "green"
        reason = "The customer expressly authorized use of the statement Green category as evidence for this review."
    else:
        return {
            "eligibility": "unknown",
            "reason": "Green eligibility cannot be confirmed from the supplied evidence.",
            "recorded_points": recorded,
            "error": None
        }

    rate = 5 if eligibility == "green" else 1
    expected = int((amount * Decimal(rate)).to_integral_value(rounding=ROUND_FLOOR))
    difference = expected - recorded
    return {
        "error": None,
        "eligibility": eligibility,
        "eligibility_reason": reason,
        "rate_points_per_dollar": rate,
        "transaction_amount": format(amount, "f"),
        "recorded_points": recorded,
        "expected_points": expected,
        "point_difference": difference,
        "under_awarded": difference > 0
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps(output_error("Input must be one valid JSON object.")))
        return
    if not isinstance(payload, dict):
        print(json.dumps(output_error("Input must be a JSON object.")))
        return
    print(json.dumps(review(payload), sort_keys=True))


if __name__ == "__main__":
    main()
