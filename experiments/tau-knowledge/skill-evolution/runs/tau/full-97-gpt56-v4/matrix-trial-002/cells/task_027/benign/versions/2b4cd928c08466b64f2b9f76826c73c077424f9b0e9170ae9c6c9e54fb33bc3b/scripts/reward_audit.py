#!/usr/bin/env python3
"""Audit rewards transactions. Reads one JSON object from stdin and writes JSON."""

import json
import sys
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

BUSINESS = "business silver rewards card"
SILVER = "silver rewards card"
PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)
QUALIFYING_CATEGORIES = {"travel", "software"}
EXCLUDED_MERCHANTS = (
    "concur", "sap concur", "expensify", "navan",
    "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online",
    "coursera", "udemy", "linkedin learning", "skillshare", "pluralsight",
)


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("must be a YYYY-MM-DD string")
    return datetime.strptime(value, "%Y-%m-%d").date()


def add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def normal(value):
    return " ".join(str(value or "").casefold().split())


def excluded_merchant(merchant):
    name = normal(merchant)
    return any(token in name for token in EXCLUDED_MERCHANTS)


def whole_points(amount, rate):
    # Dollars × percent × 100 points per dollar of cash back.
    raw = amount * rate * Decimal("100")
    return int(raw.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def account_open_dates(accounts):
    result = {}
    errors = []
    for idx, account in enumerate(accounts):
        card = normal(account.get("card_type"))
        if card not in (BUSINESS, SILVER):
            continue
        try:
            opened = parse_date(account.get("date_of_account_open"))
        except ValueError as exc:
            errors.append({"record": "account", "index": idx, "error": "invalid opening date: %s" % exc})
            continue
        if card in result and result[card] != opened:
            errors.append({"record": "account", "index": idx, "error": "conflicting opening dates for card type"})
            continue
        result[card] = opened
    return result, errors


def audit_transaction(txn, openings):
    txid = txn.get("transaction_id")
    card = normal(txn.get("credit_card_type"))
    if card not in (BUSINESS, SILVER):
        return None, {"transaction_id": txid, "reason": "unsupported card type"}
    if normal(txn.get("status")) != "completed":
        return None, {"transaction_id": txid, "reason": "not a completed transaction"}
    try:
        amount = Decimal(str(txn.get("transaction_amount")).replace("$", "").replace(",", ""))
        if amount < 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        return None, {"transaction_id": txid, "reason": "invalid transaction amount"}
    try:
        transaction_date = parse_date(txn.get("transaction_date"))
    except ValueError:
        return None, {"transaction_id": txid, "reason": "invalid transaction date"}
    try:
        actual = int(Decimal(str(txn.get("rewards_earned"))))
    except (InvalidOperation, ValueError, TypeError):
        return None, {"transaction_id": txid, "reason": "invalid rewards_earned"}

    category = normal(txn.get("category"))
    if not category:
        return None, {"transaction_id": txid, "reason": "missing posted merchant category"}

    qualifying = category in QUALIFYING_CATEGORIES
    excluded = excluded_merchant(txn.get("merchant_name"))
    if card == BUSINESS:
        if card not in openings:
            return None, {"transaction_id": txid, "reason": "missing Business Silver account opening date"}
        base_rate = Decimal("0.10") if qualifying and not excluded else Decimal("0.01")
        opened = openings[card]
        promo_eligible = PROMO_START <= opened <= PROMO_END
        promo_end = add_months(opened, 6)
        in_promo = promo_eligible and opened <= transaction_date < promo_end
        multiplier = 2 if in_promo else 1
    else:
        base_rate = Decimal("0.04") if qualifying else Decimal("0.01")
        promo_eligible = False
        promo_end = None
        in_promo = False
        multiplier = 1

    expected = whole_points(amount, base_rate * multiplier)
    difference = expected - actual
    return {
        "transaction_id": txid,
        "card_type": txn.get("credit_card_type"),
        "merchant_name": txn.get("merchant_name"),
        "transaction_date": txn.get("transaction_date"),
        "amount": format(amount, ".2f"),
        "category": txn.get("category"),
        "excluded_merchant": excluded,
        "base_rate_percent": format(base_rate * 100, "f"),
        "promotion_applied": in_promo,
        "promotion_multiplier": multiplier,
        "promotion_end_exclusive": promo_end.isoformat() if promo_eligible else None,
        "expected_points": expected,
        "actual_points": actual,
        "point_shortfall": difference,
        "cash_difference": format(Decimal(difference) / Decimal("100"), ".2f"),
        "result": "shortfall" if difference > 0 else ("over_credit" if difference < 0 else "matches")
    }, None


def main(payload):
    if not isinstance(payload, dict):
        return {"errors": [{"record": "input", "error": "top-level JSON must be an object"}]}
    accounts = payload.get("accounts", [])
    transactions = payload.get("transactions", [])
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        return {"errors": [{"record": "input", "error": "accounts and transactions must be arrays"}]}

    openings, errors = account_open_dates(accounts)
    audited, review_needed = [], []
    for txn in transactions:
        if not isinstance(txn, dict):
            review_needed.append({"transaction_id": None, "reason": "transaction is not an object"})
            continue
        record, review = audit_transaction(txn, openings)
        if record is not None:
            audited.append(record)
        else:
            review_needed.append(review)

    discrepancies = [r for r in audited if r["point_shortfall"] != 0]
    expected_total = sum(r["expected_points"] for r in audited)
    actual_total = sum(r["actual_points"] for r in audited)
    positive_shortfall = sum(r["point_shortfall"] for r in audited if r["point_shortfall"] > 0)
    return {
        "audited_transactions": audited,
        "discrepancies": discrepancies,
        "review_needed": review_needed,
        "errors": errors,
        "summary": {
            "completed_transactions_audited": len(audited),
            "transactions_requiring_review": len(review_needed),
            "total_expected_points": expected_total,
            "total_actual_points": actual_total,
            "net_point_difference": expected_total - actual_total,
            "total_positive_shortfall_points": positive_shortfall,
            "total_positive_shortfall_cash": format(Decimal(positive_shortfall) / Decimal("100"), ".2f")
        }
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), indent=2, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"errors": [{"record": "input", "error": "invalid JSON: %s" % exc}]}, indent=2))
        sys.exit(2)
