#!/usr/bin/env python3
"""Analyze documented Silver and Business Silver cash-back earning.

Reads one JSON object from stdin and writes one JSON report to stdout. See SKILL.md
for the schema. This utility is calculation only: it performs no banking action.
"""
import calendar
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

BUSINESS = "Business Silver Rewards Card"
SILVER = "Silver Rewards Card"
PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)
BONUS_CATEGORIES = {"travel", "software"}
EXCEPTION_BRANDS = (
    "sap concur", "concur", "expensify", "navan", "apple", "microsoft",
    "dell", "xbox game pass", "playstation plus", "nintendo switch online",
    "coursera", "udemy", "linkedin learning", "skillshare", "pluralsight",
)


def parse_date(value):
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def money_to_cents(value):
    amount = Decimal(str(value))
    if amount < 0:
        raise ValueError("transaction_amount cannot be negative")
    return (amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def to_int_points(value):
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def cash_string(points):
    return format((Decimal(points) / Decimal("100")).quantize(Decimal("0.01")), ".2f")


def norm(value):
    return " ".join(str(value or "").casefold().split())


def is_exception(merchant):
    name = norm(merchant)
    # Brand wording may include a product suffix (for example, a vendor service).
    return any(brand in name for brand in EXCEPTION_BRANDS)


def account_index(accounts):
    by_id, by_type = {}, {}
    for account in accounts:
        if account.get("account_id"):
            by_id[str(account["account_id"])] = account
        card_type = account.get("card_type")
        if card_type:
            by_type.setdefault(card_type, []).append(account)
    return by_id, by_type


def resolve_account(txn, by_id, by_type):
    supplied_id = txn.get("account_id")
    if supplied_id not in (None, ""):
        return by_id.get(str(supplied_id)), None if str(supplied_id) in by_id else "transaction account_id is not in accounts"
    candidates = by_type.get(txn.get("credit_card_type"), [])
    if len(candidates) == 1:
        return candidates[0], None
    if not candidates:
        return None, "no matching account was supplied"
    return None, "multiple accounts share this card type; transaction account_id is required"


def expected_rate(txn, account):
    card_type = txn.get("credit_card_type")
    category_bonus = norm(txn.get("category")) in BONUS_CATEGORIES
    if card_type == SILVER:
        return Decimal("0.04") if category_bonus else Decimal("0.01"), "Silver Rewards documented rate"
    if card_type != BUSINESS:
        raise ValueError("unsupported card type")
    base = Decimal("0.01") if (not category_bonus or is_exception(txn.get("merchant_name"))) else Decimal("0.10")
    opened = parse_date(account["date_of_account_open"])
    txn_date = parse_date(txn["transaction_date"])
    promo_eligible = PROMO_START <= opened <= PROMO_END
    if promo_eligible and opened <= txn_date < add_months(opened, 6):
        return base * 2, "Business Silver promotional doubled rate"
    return base, "Business Silver standard rate"


def analyze(txn, account):
    cents = money_to_cents(txn["transaction_amount"])
    rate, basis = expected_rate(txn, account)
    expected = int((cents * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    actual = to_int_points(txn["rewards_earned"])
    return {
        "transaction_id": txn.get("transaction_id"),
        "card_type": txn.get("credit_card_type"),
        "transaction_date": str(txn.get("transaction_date")),
        "merchant_name": txn.get("merchant_name"),
        "category": txn.get("category"),
        "transaction_amount": format(Decimal(cents) / Decimal("100"), ".2f"),
        "rate_percent": format(rate * 100, "f"),
        "rate_basis": basis,
        "actual_points": actual,
        "actual_cash": cash_string(actual),
        "expected_points": expected,
        "expected_cash": cash_string(expected),
        "difference_points": expected - actual,
        "difference_cash": cash_string(expected - actual),
    }


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    accounts = payload.get("accounts", [])
    transactions = payload.get("transactions", [])
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        raise ValueError("accounts and transactions must be arrays")
    # Validate supplied as-of date when present; it is retained for audit context.
    if payload.get("as_of_date"):
        parse_date(payload["as_of_date"])
    by_id, by_type = account_index(accounts)
    report = {"analyzed": [], "discrepancies": [], "matches": [], "manual_review": []}
    for txn in transactions:
        identifier = txn.get("transaction_id")
        if not isinstance(txn, dict):
            report["manual_review"].append({"transaction_id": None, "reason": "transaction is not an object"})
            continue
        if norm(txn.get("status")) != "completed":
            report["manual_review"].append({"transaction_id": identifier, "reason": "transaction is not COMPLETED"})
            continue
        card_type = txn.get("credit_card_type")
        if card_type not in (BUSINESS, SILVER):
            report["manual_review"].append({"transaction_id": identifier, "reason": "unsupported card type"})
            continue
        account, account_error = resolve_account(txn, by_id, by_type)
        if card_type == BUSINESS and account_error:
            report["manual_review"].append({"transaction_id": identifier, "reason": account_error})
            continue
        try:
            item = analyze(txn, account)
        except (KeyError, ValueError, InvalidOperation) as exc:
            report["manual_review"].append({"transaction_id": identifier, "reason": "invalid transaction data: " + str(exc)})
            continue
        report["analyzed"].append(item)
        if item["difference_points"] == 0:
            report["matches"].append(item)
        else:
            report["discrepancies"].append(item)
    return report


if __name__ == "__main__":
    try:
        result = main(json.load(sys.stdin))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
