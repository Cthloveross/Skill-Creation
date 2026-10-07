#!/usr/bin/env python3
"""Analyze known Gold Rewards Card and EcoCard earning rules.

Input and output are JSON objects on stdin/stdout. No external dependencies are used.
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

EXCLUDED_ECO_MERCHANTS = {"target", "walmart", "amazon", "thredup"}
CERTIFIED_EV_NETWORKS = {"tesla supercharger", "chargepoint", "evgo"}
# These labels correspond to categories described as generally green. A transaction
# labeled Green is treated as ledger evidence of that classification.
GREEN_CATEGORY_LABELS = {
    "green",
    "public transit",
    "public transportation",
    "renewable energy",
    "renewable energy subscription",
    "bike share",
    "micromobility",
    "certified sustainable retailer",
    "eco-labeled products",
}
EV_CATEGORY_LABELS = {"ev charging", "electric vehicle charging"}


def normalized(value):
    return " ".join(str(value or "").strip().casefold().split())


def parse_decimal(value, field):
    """Parse a number or a display string such as '$12.34' or '25 points'."""
    if isinstance(value, bool) or value is None:
        raise ValueError("%s is missing or not numeric" % field)
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    elif isinstance(value, str):
        text = value.replace(",", "").replace("$", "").strip()
        match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
        if not match:
            raise ValueError("%s is not numeric" % field)
        text = match.group(0)
    else:
        raise ValueError("%s is not numeric" % field)
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("%s is not numeric" % field) from exc


def whole_points(value):
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def eco_rate(merchant, category):
    """Return (rate, basis), or (None, explanation) when not decidable."""
    merchant_key = normalized(merchant)
    category_key = normalized(category)
    if merchant_key in EXCLUDED_ECO_MERCHANTS:
        return Decimal("1"), "EcoCard explicit merchant exclusion"
    if merchant_key in CERTIFIED_EV_NETWORKS:
        return Decimal("5"), "EcoCard certified EV charging network"
    if category_key in EV_CATEGORY_LABELS:
        return Decimal("1"), "EcoCard EV charging requires a named certified network"
    if category_key in GREEN_CATEGORY_LABELS:
        return Decimal("5"), "EcoCard qualifying green category recorded on transaction"
    if category_key:
        return Decimal("1"), "EcoCard non-green transaction category"
    return None, "EcoCard qualification cannot be determined without a transaction category or recognized merchant"


def add_review(result, transaction, reason):
    result["review_required"].append({
        "transaction_id": transaction.get("transaction_id"),
        "reason": reason,
    })


def analyze_transaction(transaction, result):
    if not isinstance(transaction, dict):
        result["review_required"].append({"transaction_id": None, "reason": "transaction record is not an object"})
        return
    transaction_id = transaction.get("transaction_id")
    if not transaction_id:
        add_review(result, transaction, "missing transaction_id")
        return
    if normalized(transaction.get("status")) != "completed":
        add_review(result, transaction, "only positive COMPLETED transactions can be compared")
        return
    try:
        amount = parse_decimal(transaction.get("transaction_amount"), "transaction_amount")
        posted = parse_decimal(transaction.get("rewards_earned"), "rewards_earned")
    except ValueError as exc:
        add_review(result, transaction, str(exc))
        return
    if amount <= 0:
        add_review(result, transaction, "nonpositive amount may be a return or adjustment; original earn rate is needed")
        return
    if posted != posted.to_integral_value():
        add_review(result, transaction, "posted rewards are not whole points")
        return

    card_type = normalized(transaction.get("credit_card_type"))
    if card_type == "gold rewards card":
        rate = Decimal("2.5")
        basis = "Gold Rewards Card 2.5% cash back"
    elif card_type == "ecocard":
        rate, basis = eco_rate(transaction.get("merchant_name"), transaction.get("category"))
        if rate is None:
            add_review(result, transaction, basis)
            return
    else:
        add_review(result, transaction, "earning rate is not established for this card type")
        return

    expected = whole_points(amount * rate)
    posted_int = int(posted)
    difference = expected - posted_int
    entry = {
        "transaction_id": str(transaction_id),
        "card_type": transaction.get("credit_card_type"),
        "merchant_name": transaction.get("merchant_name"),
        "transaction_date": transaction.get("transaction_date"),
        "amount": format(amount, ".2f"),
        "posted_points": posted_int,
        "expected_points": expected,
        "difference_points": difference,
        "difference_value_dollars": format(Decimal(abs(difference)) * Decimal("0.01"), ".2f"),
        "points_per_dollar": str(rate),
        "basis": basis,
        "rounding": "expected points are floored per transaction",
    }
    if difference:
        entry["direction"] = "under_awarded" if difference > 0 else "over_awarded"
        result["discrepancies"].append(entry)
    else:
        result["matches"].append(entry)


def account_values(accounts, result):
    if accounts is None:
        return
    if not isinstance(accounts, list):
        result["input_errors"].append("accounts must be an array when supplied")
        return
    for account in accounts:
        if not isinstance(account, dict):
            result["review_required"].append({"account_id": None, "reason": "account record is not an object"})
            continue
        try:
            points = parse_decimal(account.get("reward_points"), "reward_points")
        except ValueError as exc:
            result["review_required"].append({"account_id": account.get("account_id"), "reason": str(exc)})
            continue
        if points < 0 or points != points.to_integral_value():
            result["review_required"].append({"account_id": account.get("account_id"), "reason": "account reward_points must be a nonnegative whole number"})
            continue
        result["account_reward_values"].append({
            "account_id": account.get("account_id"),
            "card_type": account.get("card_type"),
            "reward_points": int(points),
            "redemption_value_dollars": format(points * Decimal("0.01"), ".2f"),
        })


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": "invalid JSON input: %s" % exc}))
        return
    if not isinstance(payload, dict):
        print(json.dumps({"ok": False, "error": "input must be a JSON object"}))
        return
    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        print(json.dumps({"ok": False, "error": "transactions must be an array"}))
        return

    result = {
        "ok": True,
        "analyzed_count": 0,
        "discrepancies": [],
        "matches": [],
        "review_required": [],
        "account_reward_values": [],
        "input_errors": [],
        "value_per_point_dollars": "0.01",
    }
    for transaction in transactions:
        before = len(result["discrepancies"]) + len(result["matches"])
        analyze_transaction(transaction, result)
        after = len(result["discrepancies"]) + len(result["matches"])
        if after > before:
            result["analyzed_count"] += 1
    account_values(payload.get("accounts"), result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
