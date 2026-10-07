#!/usr/bin/env python3
"""Calculate expected posted rewards for the Business Silver and Silver cards.

Input and output are JSON objects on stdin/stdout. This script is deliberately
read-only: update_candidates are calculation outputs, not authorization to
change any bank record.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

BUSINESS = "Business Silver Rewards Card"
SILVER = "Silver Rewards Card"
POSTED = {"COMPLETED", "POSTED"}
EXCLUSIONS = (
    "Concur", "SAP Concur", "Expensify", "Navan", "Apple", "Microsoft",
    "Dell", "Xbox Game Pass", "PlayStation Plus", "Nintendo Switch Online",
    "Coursera", "Udemy", "LinkedIn Learning", "Skillshare", "Pluralsight",
)
PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)


def fail(message):
    print(json.dumps({"error": message}, sort_keys=True))
    raise SystemExit(2)


def as_date(value, field):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be YYYY-MM-DD")


def amount(value):
    try:
        return Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        raise ValueError("transaction_amount must be a decimal amount")


def points(value):
    text = str(value).strip().lower().replace("points", "").strip()
    try:
        parsed = Decimal(text)
    except InvalidOperation:
        raise ValueError("rewards_earned must be a whole point value")
    if parsed != parsed.to_integral_value():
        raise ValueError("rewards_earned must be a whole point value")
    return int(parsed)


def add_months(value, months):
    """Calendar addition, clamping day for shorter target months."""
    index = value.month - 1 + months
    year, month = value.year + index // 12, index % 12 + 1
    month_lengths = (31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                     31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    return date(year, month, min(value.day, month_lengths[month - 1]))


def normalized(text):
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in str(text)).split())


def is_excluded(merchant):
    candidate = normalized(merchant)
    for exclusion in EXCLUSIONS:
        token = normalized(exclusion)
        if candidate == token or candidate.startswith(token + " "):
            return True
    return False


def rate_for(tx, opened):
    card = tx["credit_card_type"]
    category = normalized(tx["category"])
    txn_date = as_date(tx["transaction_date"], "transaction_date")
    if txn_date < opened:
        return None, "transaction predates account opening"
    eligible = category in {"travel", "software"}
    if card == SILVER:
        return (Decimal("0.04") if eligible else Decimal("0.01")), None
    if card != BUSINESS:
        return None, "unsupported card type"

    base = Decimal("0.10") if eligible and not is_excluded(tx["merchant_name"]) else Decimal("0.01")
    if not (PROMO_START <= opened <= PROMO_END):
        return base, None
    anniversary = add_months(opened, 6)
    if txn_date == anniversary:
        return None, "six-month promotional boundary requires current-program review"
    if opened <= txn_date < anniversary:
        return base * 2, None
    return base, None


def audit_one(tx, openings, approved):
    required = ("transaction_id", "credit_card_type", "merchant_name", "transaction_amount",
                "transaction_date", "category", "status", "rewards_earned")
    missing = [key for key in required if key not in tx]
    identifier = tx.get("transaction_id", "<missing transaction_id>")
    if missing:
        return "review", {"transaction_id": identifier, "reason": "missing fields: " + ", ".join(missing)}
    card = tx["credit_card_type"]
    if card not in openings:
        return "review", {"transaction_id": identifier, "reason": "no account opening date for card type"}
    if str(tx["status"]).upper() not in POSTED:
        return "review", {"transaction_id": identifier, "reason": "transaction is not posted/completed"}
    try:
        opened = openings[card]
        rate, reason = rate_for(tx, opened)
        if reason:
            return "review", {"transaction_id": identifier, "reason": reason}
        purchase = amount(tx["transaction_amount"])
        actual = points(tx["rewards_earned"])
        if purchase < 0:
            return "review", {"transaction_id": identifier, "reason": "negative amount requires refund/credit review"}
        expected = int((purchase * Decimal(100) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except ValueError as exc:
        return "review", {"transaction_id": identifier, "reason": str(exc)}

    result = {
        "transaction_id": identifier,
        "card_type": card,
        "expected_points": expected,
        "actual_points": actual,
        "difference_points": expected - actual,
        "rate_percent": str(rate * 100),
    }
    if expected == actual:
        return "match", result
    result["finding"] = "shortchanged" if expected > actual else "overcredited"
    if expected > actual and identifier in approved:
        result["update_payload"] = {"transaction_id": identifier, "new_rewards_earned": f"{expected} points"}
    return "discrepancy", result


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON input: {exc.msg}")
    if not isinstance(payload, dict):
        fail("input must be a JSON object")
    accounts = payload.get("accounts")
    transactions = payload.get("transactions")
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        fail("accounts and transactions must both be lists")

    openings = {}
    try:
        for account in accounts:
            card = account["card_type"]
            opened = as_date(account["date_of_account_open"], "date_of_account_open")
            if card in openings and openings[card] != opened:
                fail("multiple conflicting opening dates for the same card type")
            openings[card] = opened
    except (KeyError, TypeError, ValueError) as exc:
        fail(f"invalid accounts entry: {exc}")

    approved_raw = payload.get("resolved_dispute_transaction_ids", [])
    if not isinstance(approved_raw, list):
        fail("resolved_dispute_transaction_ids must be a list when supplied")
    approved = {str(item) for item in approved_raw}

    output = {"matches": [], "discrepancies": [], "review_items": [], "update_candidates": []}
    for tx in transactions:
        if not isinstance(tx, dict):
            output["review_items"].append({"transaction_id": "<unknown>", "reason": "transaction must be an object"})
            continue
        bucket, result = audit_one(tx, openings, approved)
        output[{"match": "matches", "discrepancy": "discrepancies", "review": "review_items"}[bucket]].append(result)
        if bucket == "discrepancy" and "update_payload" in result:
            output["update_candidates"].append(result["update_payload"])

    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
