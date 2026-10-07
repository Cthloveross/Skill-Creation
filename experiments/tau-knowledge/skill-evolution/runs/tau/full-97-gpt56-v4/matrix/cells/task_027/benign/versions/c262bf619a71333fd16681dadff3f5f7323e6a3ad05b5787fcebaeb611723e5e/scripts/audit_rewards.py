#!/usr/bin/env python3
"""Audit posted Silver and Business Silver rewards.

Reads one JSON object from stdin and writes one JSON object to stdout.  See
SKILL.md for the public schema.  Errors are emitted as {"error": "..."} and
cause a nonzero exit status.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

BUSINESS = "Business Silver Rewards Card"
PERSONAL = "Silver Rewards Card"
QUALIFYING_CATEGORIES = {"travel", "software"}
EXCLUSIONS = (
    "concur", "sap concur", "expensify", "navan", "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online", "coursera",
    "udemy", "linkedin learning", "skillshare", "pluralsight",
)
DEFAULT_PROMO = {"start_date": "2024-11-14", "end_date": "2025-11-14", "months": 6}


def parse_date(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO date (YYYY-MM-DD)") from exc


def parse_amount(value, label):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} must be a decimal amount") from exc
    if amount < 0:
        raise ValueError(f"{label} cannot be negative")
    return amount


def parse_points(value, label):
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    try:
        points = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer") from exc
    if str(value).strip() not in {str(points), f"{points}.0"} if isinstance(value, str) else False:
        raise ValueError(f"{label} must be a whole number")
    return points


def add_months(source, months):
    """Return same calendar day months later, clamped for shorter months."""
    month_index = source.month - 1 + months
    year = source.year + month_index // 12
    month = month_index % 12 + 1
    days = (31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    return date(year, month, min(source.day, days[month - 1]))


def normalized(value):
    return " ".join(str(value).casefold().split())


def excluded_merchant(merchant):
    name = normalized(merchant)
    # Names in transaction feeds can include product/service suffixes.
    return next((item for item in EXCLUSIONS if name == item or name.startswith(item + " ")), None)


def promotion_config(raw):
    if raw is None:
        raw = DEFAULT_PROMO
    if not isinstance(raw, dict):
        raise ValueError("promotion must be an object")
    start = parse_date(raw.get("start_date"), "promotion.start_date")
    end = parse_date(raw.get("end_date"), "promotion.end_date")
    months = raw.get("months", 6)
    if not isinstance(months, int) or isinstance(months, bool) or months < 1:
        raise ValueError("promotion.months must be a positive integer")
    if end < start:
        raise ValueError("promotion end date precedes start date")
    return start, end, months


def expected_rate(card_type, opened, tx_date, category, merchant, promo):
    category_is_eligible = normalized(category) in QUALIFYING_CATEGORIES
    if card_type == PERSONAL:
        if category_is_eligible:
            return Decimal("4"), "personal Silver posted Travel/Software category"
        return Decimal("1"), "personal Silver standard category"

    exclusion = excluded_merchant(merchant)
    if exclusion:
        base, reason = Decimal("1"), f"Business Silver exclusion: {exclusion}"
    elif category_is_eligible:
        base, reason = Decimal("10"), "Business Silver posted Travel/Software category"
    else:
        base, reason = Decimal("1"), "Business Silver standard category"

    promo_start, promo_end, promo_months = promo
    account_qualifies = promo_start <= opened <= promo_end
    promo_ends = add_months(opened, promo_months)
    if account_qualifies and opened <= tx_date < promo_ends:
        return base * 2, reason + "; double-cash-back promotional period"
    if not account_qualifies:
        return base, reason + "; account was not opened during promotion"
    return base, reason + "; outside six-month promotional period"


def audit(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    account = payload.get("account")
    transactions = payload.get("transactions")
    if not isinstance(account, dict):
        raise ValueError("account must be an object")
    if not isinstance(transactions, list):
        raise ValueError("transactions must be an array")
    card_type = account.get("card_type")
    if card_type not in {BUSINESS, PERSONAL}:
        raise ValueError("unsupported card_type; expected Silver Rewards Card or Business Silver Rewards Card")
    opened = parse_date(account.get("date_of_account_open"), "account.date_of_account_open")
    promo = promotion_config(payload.get("promotion"))

    reviewed, skipped = [], []
    under_points = over_points = 0
    for index, tx in enumerate(transactions):
        if not isinstance(tx, dict):
            raise ValueError(f"transactions[{index}] must be an object")
        txid = tx.get("transaction_id", f"transaction[{index}]")
        status = normalized(tx.get("status", ""))
        if status != "completed":
            skipped.append({"transaction_id": txid, "reason": "not a completed/posted transaction", "status": tx.get("status")})
            continue
        for field in ("merchant_name", "transaction_amount", "transaction_date", "category", "rewards_earned"):
            if field not in tx:
                raise ValueError(f"transactions[{index}].{field} is required for a completed transaction")
        tx_date = parse_date(tx["transaction_date"], f"transactions[{index}].transaction_date")
        amount = parse_amount(tx["transaction_amount"], f"transactions[{index}].transaction_amount")
        recorded = parse_points(tx["rewards_earned"], f"transactions[{index}].rewards_earned")
        rate, reason = expected_rate(card_type, opened, tx_date, tx["category"], tx["merchant_name"], promo)
        expected = int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))
        difference = expected - recorded
        if difference > 0:
            finding = "undercredited"
            under_points += difference
        elif difference < 0:
            finding = "overcredited"
            over_points += -difference
        else:
            finding = "match"
        reviewed.append({
            "transaction_id": txid,
            "transaction_date": tx["transaction_date"],
            "merchant_name": tx["merchant_name"],
            "posted_category": tx["category"],
            "transaction_amount": format(amount, "f"),
            "rate_percent": format(rate, "f"),
            "rate_reason": reason,
            "expected_points": expected,
            "recorded_points": recorded,
            "point_difference": difference,
            "cash_difference": format(Decimal(difference) / Decimal(100), ".2f"),
            "finding": finding,
        })
    return {
        "card_type": card_type,
        "account_open_date": opened.isoformat(),
        "reviewed": reviewed,
        "skipped": skipped,
        "summary": {
            "reviewed_count": len(reviewed),
            "skipped_count": len(skipped),
            "matching_count": sum(row["finding"] == "match" for row in reviewed),
            "undercredited_count": sum(row["finding"] == "undercredited" for row in reviewed),
            "overcredited_count": sum(row["finding"] == "overcredited" for row in reviewed),
            "total_apparent_missing_points": under_points,
            "total_apparent_missing_cash": format(Decimal(under_points) / Decimal(100), ".2f"),
            "total_apparent_excess_points": over_points,
            "total_apparent_excess_cash": format(Decimal(over_points) / Decimal(100), ".2f"),
        },
    }


def main():
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(audit(payload), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
