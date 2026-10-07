#!/usr/bin/env python3
"""Review transaction rewards using documented card rules.

Input:  {"transactions": [transaction, ...]} on stdin.
Output: JSON with possible_discrepancies, matches, potential_overpayments,
         manual_review, and summary on stdout.

This script is deterministic and performs no network, file, or banking-tool access.
"""
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN

EXCLUDED_ECO_MERCHANTS = {"target", "walmart", "amazon", "thredup"}
CERTIFIED_EV_NETWORKS = {"tesla supercharger", "chargepoint", "evgo"}
ELIGIBILITY_FLAGS = (
    "is_cash_equivalent",
    "is_balance_transfer",
    "is_fee",
    "is_return_or_credit",
)
REQUIRED_FIELDS = (
    "transaction_id",
    "credit_card_type",
    "merchant_name",
    "transaction_amount",
    "transaction_date",
    "category",
    "status",
    "rewards_earned",
)


def normalized(value):
    """Normalize a comparison value without changing the value reported to users."""
    return " ".join(str(value or "").casefold().split())


def parse_amount(value):
    if isinstance(value, bool):
        raise ValueError("transaction_amount must not be boolean")
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("invalid transaction_amount") from exc
    if not amount.is_finite():
        raise ValueError("transaction_amount must be finite")
    return amount


def parse_points(value):
    if isinstance(value, bool):
        raise ValueError("rewards_earned must not be boolean")
    match = re.search(r"-?\d+", str(value))
    if not match:
        raise ValueError("rewards_earned must contain a whole number")
    return int(match.group(0))


def whole_points(amount, rate):
    """Calculate whole points by truncating any fractional point down."""
    return int((amount * rate).to_integral_value(rounding=ROUND_DOWN))


def has_exclusion_flag(txn):
    return any(bool(txn.get(flag, False)) for flag in ELIGIBILITY_FLAGS)


def expected_rate(txn):
    """Return (rate, explanation) or (None, manual-review explanation)."""
    card = normalized(txn.get("credit_card_type"))
    category = normalized(txn.get("category"))
    merchant = normalized(txn.get("merchant_name"))

    if has_exclusion_flag(txn):
        return None, (
            "Transaction is marked as a fee, cash equivalent, balance transfer, "
            "or return/credit and is not evaluated as an eligible completed purchase."
        )

    if card == "crypto-cash back":
        return Decimal("0.02"), "Crypto-Cash Back eligible-purchase rate: 2.0%."

    if card == "silver rewards card":
        if category in {"travel", "software"}:
            return Decimal("0.04"), "Silver Rewards qualifying Travel/Software rate: 4.0%."
        return None, "Silver Rewards base rate is not established by the available policy."

    if card == "business platinum rewards card":
        if category in {"travel", "software", "media"}:
            return Decimal("0.04"), "Business Platinum Travel/Software/Media rate: 4.0%."
        return Decimal("0.015"), "Business Platinum other-purchase rate: 1.5%."

    if card == "ecocard":
        if merchant in EXCLUDED_ECO_MERCHANTS:
            return Decimal("1"), "EcoCard excluded-merchant standard rate: 1 point per dollar."
        ev_like = any(term in merchant for term in ("charging", "charger", "charge"))
        if ev_like and merchant not in CERTIFIED_EV_NETWORKS:
            return Decimal("1"), "EcoCard non-certified EV-charging standard rate: 1 point per dollar."
        if category in {"green", "sustainable"}:
            return Decimal("5"), "EcoCard qualifying Green/Sustainable rate: 5 points per dollar."
        return Decimal("1"), "EcoCard other-purchase standard rate: 1 point per dollar."

    return None, "Card type is not supported by the available documented reward rules."


def manual(txn, reason):
    return {
        "transaction_id": txn.get("transaction_id"),
        "merchant_name": txn.get("merchant_name"),
        "transaction_date": txn.get("transaction_date"),
        "reason": reason,
    }


def evaluate(txn):
    missing = [field for field in REQUIRED_FIELDS if txn.get(field) is None or txn.get(field) == ""]
    if missing:
        return "manual_review", manual(txn, "Missing required field(s): " + ", ".join(missing))
    if normalized(txn["status"]) != "completed":
        return "manual_review", manual(txn, "Transaction is not completed.")

    try:
        amount = parse_amount(txn["transaction_amount"])
        recorded = parse_points(txn["rewards_earned"])
    except ValueError as exc:
        return "manual_review", manual(txn, str(exc))
    if amount <= 0:
        return "manual_review", manual(txn, "Nonpositive transaction amount requires review.")
    if recorded < 0:
        return "manual_review", manual(txn, "Negative recorded rewards require review.")

    rate, rule = expected_rate(txn)
    if rate is None:
        return "manual_review", manual(txn, rule)

    expected = whole_points(amount, rate)
    difference = expected - recorded
    finding = {
        "transaction_id": txn["transaction_id"],
        "merchant_name": txn["merchant_name"],
        "transaction_date": txn["transaction_date"],
        "credit_card_type": txn["credit_card_type"],
        "category": txn["category"],
        "transaction_amount": format(amount, "f"),
        "documented_rate": format(rate, "f"),
        "rate_rule": rule,
        "recorded_points": recorded,
        "expected_points": expected,
        "point_difference": difference,
    }
    if difference > 0:
        return "possible_discrepancies", finding
    if difference < 0:
        return "potential_overpayments", finding
    return "matches", finding


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "Input must be valid JSON: " + str(exc)}))
        return

    transactions = payload.get("transactions") if isinstance(payload, dict) else None
    if not isinstance(transactions, list):
        print(json.dumps({"error": "Input must be an object containing a transactions array."}))
        return

    result = {
        "possible_discrepancies": [],
        "matches": [],
        "potential_overpayments": [],
        "manual_review": [],
    }
    for txn in transactions:
        if not isinstance(txn, dict):
            result["manual_review"].append({
                "transaction_id": None,
                "reason": "Transaction must be an object.",
            })
            continue
        bucket, finding = evaluate(txn)
        result[bucket].append(finding)

    result["summary"] = {
        "transactions_received": len(transactions),
        "possible_discrepancy_count": len(result["possible_discrepancies"]),
        "match_count": len(result["matches"]),
        "potential_overpayment_count": len(result["potential_overpayments"]),
        "manual_review_count": len(result["manual_review"]),
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
