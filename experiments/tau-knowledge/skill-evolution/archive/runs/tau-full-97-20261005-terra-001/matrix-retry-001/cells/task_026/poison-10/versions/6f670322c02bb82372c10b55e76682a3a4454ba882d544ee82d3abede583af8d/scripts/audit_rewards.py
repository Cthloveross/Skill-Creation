#!/usr/bin/env python3
"""Audit posted cash-back transactions from JSON stdin.

This program is read-only: it does not call banking tools or modify records.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

BUSINESS = "Business Silver Rewards Card"
SILVER = "Silver Rewards Card"
EXCLUDED_BUSINESS_MERCHANTS = (
    "concur", "sap concur", "expensify", "navan", "apple", "microsoft",
    "dell", "xbox game pass", "playstation plus", "nintendo switch online",
    "coursera", "udemy", "linkedin learning", "skillshare", "pluralsight",
)
NON_ENHANCED_TYPES = {
    "gift card", "gift cards", "person-to-person", "p2p", "fee", "fees",
    "interest", "insurance", "insurance premium", "insurance premiums",
}


def decimal_value(value, field):
    try:
        text = str(value).strip().replace("$", "").replace(",", "")
        result = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError("invalid decimal for " + field)
    if not result.is_finite() or result < 0:
        raise ValueError(field + " must be a nonnegative finite decimal")
    return result


def parse_date(value, field):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError("invalid YYYY-MM-DD date for " + field)


def add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    month_days = (31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                  31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    return date(year, month, min(value.day, month_days[month - 1]))


def parse_points(value):
    text = str(value).strip().lower().replace("points", "").strip().replace(",", "")
    try:
        parsed = Decimal(text)
    except InvalidOperation:
        raise ValueError("invalid rewards_earned; expected whole points")
    if parsed != parsed.to_integral_value() or parsed < 0:
        raise ValueError("rewards_earned must be a nonnegative whole-point value")
    return int(parsed)


def normalise_merchant(value):
    return " ".join(str(value).casefold().split())


def is_excluded_business_merchant(merchant):
    name = normalise_merchant(merchant)
    return any(name == item or name.startswith(item + " ") for item in EXCLUDED_BUSINESS_MERCHANTS)


def is_eligible_category(category):
    return str(category).strip().casefold() in {"travel", "software", "software/saas", "saas"}


def points_for(amount, rate_percent):
    cash = amount * rate_percent / Decimal("100")
    return int((cash / Decimal("0.01")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def promotion_active(opened, transaction_day, inclusive):
    promo_start = date(2024, 11, 14)
    promo_close = date(2025, 11, 14)
    if not (promo_start <= opened <= promo_close):
        return False
    boundary = add_months(opened, 6)
    return opened <= transaction_day <= boundary if inclusive else opened <= transaction_day < boundary


def account_index(accounts):
    by_id = {}
    by_type = {}
    for account in accounts:
        account_id = account.get("account_id")
        card_type = account.get("card_type")
        if not account_id or card_type not in (BUSINESS, SILVER):
            raise ValueError("each account needs an account_id and supported card_type")
        parse_date(account.get("date_of_account_open"), "date_of_account_open")
        if account_id in by_id:
            raise ValueError("duplicate account_id")
        by_id[account_id] = account
        by_type.setdefault(card_type, []).append(account)
    return by_id, by_type


def match_account(transaction, by_id, by_type):
    account_id = transaction.get("account_id")
    if account_id:
        if account_id not in by_id:
            raise ValueError("transaction account_id has no matching account")
        return by_id[account_id]
    card_type = transaction.get("credit_card_type")
    choices = by_type.get(card_type, [])
    if len(choices) != 1:
        raise ValueError("transaction needs account_id when card type is missing or not unique")
    return choices[0]


def assess(transaction, account, silver_other_rate, promo_end_inclusive):
    tx_id = transaction.get("transaction_id")
    if not tx_id:
        raise ValueError("transaction_id is required")
    amount = decimal_value(transaction.get("transaction_amount"), "transaction_amount")
    tx_date = parse_date(transaction.get("transaction_date"), "transaction_date")
    recorded = parse_points(transaction.get("rewards_earned"))
    status = str(transaction.get("status", "")).strip().upper()
    category = str(transaction.get("category", "")).strip()
    merchant = str(transaction.get("merchant_name", "")).strip()
    result = {
        "transaction_id": tx_id,
        "account_id": account["account_id"],
        "card_type": account["card_type"],
        "recorded_points": recorded,
        "expected_points": None,
        "rate_percent": None,
        "promotion_applied": False,
        "classification": "indeterminate",
        "reason": "",
    }
    if status != "COMPLETED":
        result["reason"] = "Only completed/posted purchases are automatically evaluated."
        return result
    category_key = category.casefold()
    if category_key in NON_ENHANCED_TYPES:
        result["reason"] = "This transaction type is not eligible for the enhanced rate."
        return result
    if account["card_type"] == BUSINESS:
        rate = Decimal("10") if is_eligible_category(category) and not is_excluded_business_merchant(merchant) else Decimal("1")
        opened = parse_date(account["date_of_account_open"], "date_of_account_open")
        promo = promotion_active(opened, tx_date, promo_end_inclusive)
        if promo:
            rate *= Decimal("2")
        result["promotion_applied"] = promo
        result["rate_percent"] = str(rate)
        result["reason"] = ("Business Silver eligible travel/software rate" if is_eligible_category(category) and not is_excluded_business_merchant(merchant)
                            else "Business Silver standard rate (non-eligible category or named merchant exception)")
    elif account["card_type"] == SILVER:
        if is_eligible_category(category):
            rate = Decimal("4")
            result["rate_percent"] = str(rate)
            result["reason"] = "Silver eligible travel/software rate."
        elif silver_other_rate is not None:
            rate = silver_other_rate
            result["rate_percent"] = str(rate)
            result["reason"] = "Runtime-supplied authorized Silver non-bonus rate."
        else:
            result["reason"] = "No documented Silver non-bonus rate was supplied."
            return result
    else:
        result["reason"] = "Unsupported card type."
        return result
    expected = points_for(amount, rate)
    result["expected_points"] = expected
    difference = expected - recorded
    result["difference_points"] = difference
    if difference > 0:
        result["classification"] = "shortfall"
    elif difference < 0:
        result["classification"] = "apparent_excess"
    else:
        result["classification"] = "correct"
    return result


def main(payload):
    accounts = payload.get("accounts")
    transactions = payload.get("transactions")
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        raise ValueError("accounts and transactions must both be arrays")
    silver_rate = payload.get("silver_other_rate_percent")
    if silver_rate is not None:
        silver_rate = decimal_value(silver_rate, "silver_other_rate_percent")
    inclusive = payload.get("promo_end_inclusive", False)
    if not isinstance(inclusive, bool):
        raise ValueError("promo_end_inclusive must be boolean")
    by_id, by_type = account_index(accounts)
    assessments = [assess(tx, match_account(tx, by_id, by_type), silver_rate, inclusive) for tx in transactions]
    determinate = [item for item in assessments if item["expected_points"] is not None]
    return {
        "assessments": assessments,
        "totals": {
            "transactions": len(assessments),
            "determinate_transactions": len(determinate),
            "expected_points": sum(item["expected_points"] for item in determinate),
            "recorded_points": sum(item["recorded_points"] for item in determinate),
            "shortfall_points": sum(max(item.get("difference_points", 0), 0) for item in determinate),
        },
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": {"message": str(exc)}} , separators=(",", ":")))
        sys.exit(2)
