#!/usr/bin/env python3
"""Deterministic rewards audit. Reads one JSON object from stdin and writes one JSON object."""

import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

BRONZE = "business bronze rewards card"
ECO = "ecocard"
BRONZE_ZERO_MERCHANTS = {
    "wework", "regus", "industrious",
    "gusto", "adp", "paychex", "rippling",
}
BRONZE_SAAS = {"slack", "zoom", "hubspot", "salesforce"}
ECO_STANDARD_MERCHANTS = {"target", "walmart", "amazon", "thredup"}
ECO_GREEN_EV_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}
POSTED_STATUSES = {"completed", "posted"}


def norm(value):
    return " ".join(str(value or "").strip().casefold().split())


def as_decimal(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("missing or invalid decimal")
    try:
        result = Decimal(str(value).strip().replace("$", "").replace(",", ""))
    except (InvalidOperation, ValueError):
        raise ValueError("invalid decimal")
    if not result.is_finite():
        raise ValueError("decimal must be finite")
    return result


def parse_points(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("rewards_earned must be a whole number of points")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError("rewards_earned must be whole")
        return int(value)
    text = str(value).strip()
    match = re.fullmatch(r"([+-]?\d+)(?:\s+points?)?", text, flags=re.IGNORECASE)
    if not match:
        raise ValueError("rewards_earned must be an integer or 'N points'")
    return int(match.group(1))


def whole_points(amount, points_per_dollar):
    return int((amount * Decimal(points_per_dollar)).to_integral_value(rounding=ROUND_FLOOR))


def base_result(txn_id, card_type, merchant):
    return {
        "transaction_id": txn_id,
        "card_type": card_type,
        "merchant_name": merchant,
        "determination": None,
        "expected_points": None,
        "recorded_points": None,
        "delta_points": None,
        "rate_points_per_dollar": None,
        "rationale": [],
        "recommended_action": None,
    }


def blocked(result, determination, reason, action):
    result["determination"] = determination
    result["rationale"].append(reason)
    result["recommended_action"] = action
    return result


def audit_transaction(transaction, green_category_is_verified):
    if not isinstance(transaction, dict):
        return blocked(base_result(None, None, None), "unsupported", "Transaction record is not an object.", "repair_transaction_input")

    txn_id = transaction.get("transaction_id")
    card_type = transaction.get("card_type")
    merchant = transaction.get("merchant_name")
    result = base_result(txn_id, card_type, merchant)
    if not isinstance(txn_id, str) or not txn_id.strip():
        return blocked(result, "unsupported", "Missing transaction_id.", "repair_transaction_input")
    if not isinstance(card_type, str) or not isinstance(merchant, str) or not merchant.strip():
        return blocked(result, "unsupported", "Missing card type or merchant name.", "repair_transaction_input")

    status = transaction.get("status", "COMPLETED")
    if norm(status) not in POSTED_STATUSES:
        return blocked(result, "not_determinable", "Transaction is not a posted/completed purchase record.", "wait_for_posting_or_review_return")

    raw_amount = transaction.get("net_eligible_amount", transaction.get("transaction_amount", transaction.get("amount")))
    try:
        amount = as_decimal(raw_amount)
    except ValueError as exc:
        return blocked(result, "unsupported", "Cannot calculate from amount: " + str(exc) + ".", "repair_transaction_input")
    if amount < 0:
        return blocked(result, "not_determinable", "Negative amounts may be refunds or reversals and require the original reward context.", "review_return_or_credit")

    try:
        recorded = parse_points(transaction.get("rewards_earned"))
    except ValueError as exc:
        return blocked(result, "unsupported", str(exc) + ".", "repair_transaction_input")
    result["recorded_points"] = recorded

    card = norm(card_type)
    merchant_key = norm(merchant)
    expected = None
    rate = None

    if card == BRONZE:
        if merchant_key in BRONZE_ZERO_MERCHANTS:
            rate = Decimal("0")
            result["rationale"].append("Named Business Bronze coworking/payroll merchant exclusion: 0 points.")
        elif merchant_key in BRONZE_SAAS:
            months = transaction.get("subscription_months")
            if months is None:
                return blocked(result, "not_determinable", "Named SaaS exception requires subscription_months to determine whether the first 12 months have elapsed.", "obtain_subscription_tenure")
            try:
                months_value = as_decimal(months)
            except ValueError:
                return blocked(result, "unsupported", "subscription_months is invalid.", "repair_transaction_input")
            if months_value < 0:
                return blocked(result, "unsupported", "subscription_months cannot be negative.", "repair_transaction_input")
            rate = Decimal("0") if months_value > 12 else Decimal("1")
            if rate == 0:
                result["rationale"].append("Named Business Bronze SaaS subscription is beyond its first 12 months: 0 points.")
            else:
                result["rationale"].append("Named Business Bronze SaaS subscription is within its first 12 months: base 1 point per dollar.")
        else:
            rate = Decimal("1")
            result["rationale"].append("Business Bronze eligible net purchase: 1.0% cash back is stored as 1 point per dollar.")
    elif card == ECO:
        if merchant_key in ECO_STANDARD_MERCHANTS:
            rate = Decimal("1")
            result["rationale"].append("EcoCard named retailer/resale exclusion: standard 1 point per dollar.")
        elif merchant_key in ECO_GREEN_EV_PARTNERS:
            rate = Decimal("5")
            result["rationale"].append("EcoCard certified EV-charging partner: 5 points per dollar.")
        elif transaction.get("qualifying_green") is True:
            rate = Decimal("5")
            result["rationale"].append("Verified qualifying green purchase: 5 points per dollar.")
        elif transaction.get("qualifying_green") is False:
            rate = Decimal("1")
            result["rationale"].append("Purchase is marked non-qualifying for green rewards: standard 1 point per dollar.")
        elif green_category_is_verified and norm(transaction.get("category")) == "green":
            rate = Decimal("5")
            result["rationale"].append("Verified transaction category Green: 5 points per dollar.")
        else:
            rate = Decimal("1")
            result["rationale"].append("No verified green qualification supplied: standard 1 point per dollar.")
    else:
        return blocked(result, "unsupported", "Card type is outside this Skill's supported products.", "use_applicable_card_policy")

    expected = whole_points(amount, rate)
    result["expected_points"] = expected
    result["rate_points_per_dollar"] = str(rate)
    result["rationale"].append("Whole-point rewards are calculated by flooring fractional points.")

    if recorded is None:
        return blocked(result, "not_determinable", "No recorded rewards_earned value was supplied for comparison.", "obtain_recorded_reward")

    delta = expected - recorded
    result["delta_points"] = delta
    if delta == 0:
        result["determination"] = "correct"
        result["recommended_action"] = "none"
    elif delta > 0:
        result["determination"] = "under_awarded"
        result["recommended_action"] = "offer_customer_dispute_tool"
    else:
        result["determination"] = "over_awarded"
        result["recommended_action"] = "offer_customer_dispute_tool"
    return result


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"results": [], "summary": {}, "update_candidates": [], "input_errors": ["Invalid JSON: " + str(exc)]}))
        return

    if not isinstance(payload, dict):
        print(json.dumps({"results": [], "summary": {}, "update_candidates": [], "input_errors": ["Top-level JSON must be an object."]}))
        return
    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        print(json.dumps({"results": [], "summary": {}, "update_candidates": [], "input_errors": ["transactions must be an array."]}))
        return
    verified_green_category = payload.get("green_category_is_verified", True)
    if not isinstance(verified_green_category, bool):
        print(json.dumps({"results": [], "summary": {}, "update_candidates": [], "input_errors": ["green_category_is_verified must be boolean when supplied."]}))
        return

    results = [audit_transaction(item, verified_green_category) for item in transactions]
    determinable = [r for r in results if r["determination"] in {"correct", "under_awarded", "over_awarded"}]
    discrepancies = [r for r in results if r["determination"] in {"under_awarded", "over_awarded"}]
    candidates = [
        {"transaction_id": r["transaction_id"], "new_rewards_earned": str(r["expected_points"]) + " points", "prerequisite": "Use only after a resolved and approved dispute; independently verify before update."}
        for r in discrepancies
    ]
    summary = {
        "transactions_received": len(results),
        "determinate_transactions": len(determinable),
        "correct": sum(r["determination"] == "correct" for r in results),
        "under_awarded": sum(r["determination"] == "under_awarded" for r in results),
        "over_awarded": sum(r["determination"] == "over_awarded" for r in results),
        "not_determinable": sum(r["determination"] == "not_determinable" for r in results),
        "unsupported": sum(r["determination"] == "unsupported" for r in results),
        "expected_points_total_determinate": sum(r["expected_points"] for r in determinable),
        "recorded_points_total_determinate": sum(r["recorded_points"] for r in determinable),
    }
    print(json.dumps({"results": results, "summary": summary, "update_candidates": candidates, "input_errors": []}, ensure_ascii=False))


if __name__ == "__main__":
    main()
