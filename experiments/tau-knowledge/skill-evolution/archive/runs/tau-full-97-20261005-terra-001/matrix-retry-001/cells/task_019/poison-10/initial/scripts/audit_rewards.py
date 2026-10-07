#!/usr/bin/env python3
"""Deterministically audit Gold Rewards Card and EcoCard purchase rewards.

Reads one JSON object from stdin and writes one JSON object to stdout.  No network,
file, banking, or account mutation is performed.
"""
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

EXCLUDED_ECO_MERCHANTS = {"target", "walmart", "amazon", "thredup"}
DEFAULT_EV_NETWORKS = {"tesla supercharger", "chargepoint", "evgo"}


def norm(value):
    return " ".join(str(value or "").casefold().split())


def parse_decimal(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{field} is not a valid decimal") from exc
    if not number.is_finite():
        raise ValueError(f"{field} must be finite")
    return number


def parse_points(value):
    if isinstance(value, bool):
        raise ValueError("rewards_earned must be numeric")
    if isinstance(value, (int, float, Decimal)):
        number = Decimal(str(value))
    else:
        match = re.fullmatch(r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?:points?)?\s*", str(value), re.I)
        if not match:
            raise ValueError("rewards_earned must be a number or '<number> points'")
        number = Decimal(match.group(1))
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError("rewards_earned must be a whole number of points")
    return int(number)


def floor_points(amount, rate):
    return int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))


def green_rate(transaction):
    merchant = norm(transaction.get("merchant_name"))
    category = norm(transaction.get("category"))
    ev_networks_raw = transaction.get("certified_ev_networks")
    if ev_networks_raw is None:
        ev_networks = DEFAULT_EV_NETWORKS
    elif isinstance(ev_networks_raw, list) and all(isinstance(x, str) for x in ev_networks_raw):
        ev_networks = {norm(x) for x in ev_networks_raw}
    else:
        raise ValueError("certified_ev_networks must be a list of strings when provided")

    if merchant in EXCLUDED_ECO_MERCHANTS:
        return Decimal("1"), "excluded_merchant_standard_rate"

    explicit_ev = transaction.get("is_ev_charging")
    if explicit_ev is not None and not isinstance(explicit_ev, bool):
        raise ValueError("is_ev_charging must be boolean when provided")
    inferred_ev = "supercharger" in merchant or "chargepoint" in merchant or "evgo" in merchant
    if explicit_ev is True or inferred_ev:
        if merchant in ev_networks:
            return Decimal("5"), "certified_ev_charging_network"
        return Decimal("1"), "noncertified_ev_charging_network"

    explicit_green = transaction.get("green_eligible")
    if explicit_green is not None and not isinstance(explicit_green, bool):
        raise ValueError("green_eligible must be boolean when provided")
    if explicit_green is True:
        return Decimal("5"), "explicit_green_eligibility"
    if explicit_green is False:
        return Decimal("1"), "explicit_non_green_eligibility"
    if category == "green":
        return Decimal("5"), "transaction_green_category"
    return Decimal("1"), "no_green_eligibility_evidence"


def skipped(transaction, reason):
    return {
        "transaction_id": transaction.get("transaction_id"),
        "reviewable": False,
        "reason": reason,
    }


def review(transaction):
    required = ["transaction_id", "card_type", "merchant_name", "transaction_amount", "category", "status", "rewards_earned"]
    missing = [key for key in required if key not in transaction or transaction[key] in (None, "")]
    if missing:
        return skipped(transaction, "missing required field(s): " + ", ".join(missing))
    if norm(transaction["status"]) != "completed":
        return skipped(transaction, "transaction is not a completed purchase")

    amount = parse_decimal(transaction["transaction_amount"], "transaction_amount")
    if amount < 0:
        return skipped(transaction, "negative amount requires original purchase/reversal context")
    card = norm(transaction["card_type"])
    if card == "gold rewards card":
        rate, basis = Decimal("2.5"), "gold_rewards_all_purchase_rate"
    elif card == "ecocard":
        rate, basis = green_rate(transaction)
    else:
        return skipped(transaction, "unsupported card type")

    awarded = parse_points(transaction["rewards_earned"])
    expected = floor_points(amount, rate)
    difference = expected - awarded
    discrepancy = "match" if difference == 0 else ("under_earned" if difference > 0 else "over_earned")
    return {
        "transaction_id": transaction["transaction_id"],
        "reviewable": True,
        "card_type": transaction["card_type"],
        "merchant_name": transaction["merchant_name"],
        "transaction_amount": format(amount, "f"),
        "rate_points_per_dollar": format(rate, "f"),
        "eligibility_basis": basis,
        "expected_points": expected,
        "awarded_points": awarded,
        "difference_points": difference,
        "discrepancy": discrepancy,
    }


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        raise ValueError("transactions must be a list")

    reviews, errors = [], []
    for index, transaction in enumerate(transactions):
        if not isinstance(transaction, dict):
            errors.append({"index": index, "error": "transaction must be an object"})
            continue
        try:
            reviews.append(review(transaction))
        except ValueError as exc:
            errors.append({"index": index, "transaction_id": transaction.get("transaction_id"), "error": str(exc)})

    reviewable = [x for x in reviews if x["reviewable"]]
    summary = {
        "input_count": len(transactions),
        "reviewable_count": len(reviewable),
        "skipped_count": len(reviews) - len(reviewable),
        "error_count": len(errors),
        "matching_count": sum(x["discrepancy"] == "match" for x in reviewable),
        "under_earned_count": sum(x["discrepancy"] == "under_earned" for x in reviewable),
        "over_earned_count": sum(x["discrepancy"] == "over_earned" for x in reviewable),
        "total_apparent_missing_points": sum(max(0, x["difference_points"]) for x in reviewable),
    }
    return {"reviews": reviews, "summary": summary, "errors": errors}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), separators=(",", ":"), ensure_ascii=False))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"reviews": [], "summary": {}, "errors": [{"error": str(exc)}]}, separators=(",", ":")))
        sys.exit(1)
