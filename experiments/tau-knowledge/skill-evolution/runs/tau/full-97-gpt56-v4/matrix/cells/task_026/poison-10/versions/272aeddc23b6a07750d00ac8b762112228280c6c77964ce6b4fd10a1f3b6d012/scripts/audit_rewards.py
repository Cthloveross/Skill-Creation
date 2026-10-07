#!/usr/bin/env python3
"""Audit supported Silver Rewards transaction records from JSON stdin.

Input schema is documented in SKILL.md. Output is JSON only and has no banking side effects.
"""
import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

BUSINESS = "Business Silver Rewards Card"
PERSONAL = "Silver Rewards Card"
PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)
EXCLUDED_BUSINESS_MERCHANTS = {"microsoft", "coursera"}


def parse_date(value):
    return date.fromisoformat(str(value).strip())


def add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    month_days = (31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                  31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    return date(year, month, min(value.day, month_days[month - 1]))


def decimal_value(value, field):
    text = str(value).strip().replace(",", "").replace("$", "")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        raise ValueError("missing or invalid " + field)
    try:
        return Decimal(match.group(0))
    except InvalidOperation as exc:
        raise ValueError("missing or invalid " + field) from exc


def integer_points(value, field):
    points = decimal_value(value, field)
    if points != points.to_integral_value():
        raise ValueError(field + " must be a whole number")
    return int(points)


def money_from_points(points):
    return format(Decimal(points) / Decimal("100"), ".2f")


def normalized_merchant(value):
    return " ".join(str(value).casefold().split())


def is_excluded_business_merchant(merchant):
    normalized = normalized_merchant(merchant)
    return any(normalized == name or normalized.startswith(name + " ")
               for name in EXCLUDED_BUSINESS_MERCHANTS)


def account_open_dates(accounts):
    result = {}
    for account in accounts:
        card_type = account.get("card_type")
        if card_type in (BUSINESS, PERSONAL) and card_type not in result:
            result[card_type] = parse_date(account["date_of_account_open"])
    return result


def business_rate(transaction_date, category, merchant, opened):
    category_is_bonus = str(category).strip().casefold() in {"travel", "software"}
    excluded = is_excluded_business_merchant(merchant)
    base_rate = Decimal("0.01") if excluded or not category_is_bonus else Decimal("0.10")
    base_reason = ("business exclusion; standard rate" if excluded else
                   "eligible posted travel/software category" if category_is_bonus else
                   "non-bonus posted category; standard rate")
    promo_eligible = PROMO_START <= opened <= PROMO_END
    promo_active = promo_eligible and opened <= transaction_date < add_months(opened, 6)
    if promo_active:
        return base_rate * 2, base_reason + "; automatic double-cash-back promotion applied"
    return base_rate, base_reason


def expected_points(amount, rate):
    return int((amount * rate * Decimal("100")).to_integral_value(rounding=ROUND_FLOOR))


def audit_transaction(transaction, openings):
    transaction_id = transaction.get("transaction_id")
    card_type = transaction.get("credit_card_type")
    status = str(transaction.get("status", "")).strip().upper()
    if status != "COMPLETED":
        return None, {"transaction_id": transaction_id, "reason": "transaction is not COMPLETED"}
    if card_type not in (BUSINESS, PERSONAL):
        return None, {"transaction_id": transaction_id, "reason": "unsupported card type"}
    if card_type not in openings:
        return None, {"transaction_id": transaction_id, "reason": "matching account opening date is unavailable"}
    try:
        amount = decimal_value(transaction.get("transaction_amount"), "transaction_amount")
        if amount < 0:
            raise ValueError("transaction_amount cannot be negative")
        trans_date = parse_date(transaction.get("transaction_date"))
        actual = integer_points(transaction.get("rewards_earned"), "rewards_earned")
    except (TypeError, ValueError) as exc:
        return None, {"transaction_id": transaction_id, "reason": str(exc)}

    category = transaction.get("category")
    merchant = transaction.get("merchant_name", "")
    if card_type == PERSONAL:
        if str(category).strip().casefold() not in {"travel", "software"}:
            return None, {"transaction_id": transaction_id,
                          "reason": "personal-card regular-purchase rate is not supplied"}
        rate = Decimal("0.04")
        rule = "personal card eligible posted travel/software category"
    else:
        rate, rule = business_rate(trans_date, category, merchant, openings[BUSINESS])

    expected = expected_points(amount, rate)
    difference = expected - actual
    record = {
        "transaction_id": transaction_id,
        "card_type": card_type,
        "merchant_name": merchant,
        "transaction_date": trans_date.isoformat(),
        "category": category,
        "amount": format(amount, ".2f"),
        "rate_percent": format(rate * Decimal("100"), "f"),
        "rule": rule,
        "actual_points": actual,
        "actual_cash_back_dollars": money_from_points(actual),
        "expected_points": expected,
        "expected_cash_back_dollars": money_from_points(expected),
        "point_difference": difference,
        "difference_cash_back_dollars": money_from_points(abs(difference)),
        "status": "matches" if difference == 0 else "possible_missing_rewards" if difference > 0 else "possible_overaward_review_only",
    }
    return record, None


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        accounts = payload.get("accounts")
        transactions = payload.get("transactions")
        if not isinstance(accounts, list) or not isinstance(transactions, list):
            raise ValueError("accounts and transactions must be arrays")
        openings = account_open_dates(accounts)
    except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return

    audits = []
    not_assessable = []
    for transaction in transactions:
        if not isinstance(transaction, dict):
            not_assessable.append({"transaction_id": None, "reason": "transaction must be an object"})
            continue
        record, reason = audit_transaction(transaction, openings)
        if record is not None:
            audits.append(record)
        else:
            not_assessable.append(reason)
    discrepancies = [record for record in audits if record["point_difference"] != 0]
    print(json.dumps({"audits": audits, "discrepancies": discrepancies,
                      "not_assessable": not_assessable}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
