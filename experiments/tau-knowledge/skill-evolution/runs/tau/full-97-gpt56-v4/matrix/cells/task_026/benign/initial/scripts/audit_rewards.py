#!/usr/bin/env python3
"""Audit supported credit-card cash-back transactions.

Reads one JSON object from stdin. See SKILL.md for input and output schemas.
Uses only the Python standard library and emits JSON to stdout.
"""
from __future__ import annotations

import calendar
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from typing import Any, Dict, Iterable, List, Optional, Tuple

BUSINESS = "Business Silver Rewards Card"
SILVER = "Silver Rewards Card"
PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)
BONUS_CATEGORIES = {"travel", "software"}
EXCLUDED_BRANDS = (
    "sap concur", "concur", "expensify", "navan", "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online", "coursera",
    "udemy", "linkedin learning", "skillshare", "pluralsight",
)


def parse_date(value: Any) -> Optional[date]:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_decimal(value: Any) -> Optional[Decimal]:
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if not isinstance(value, str):
        return None
    # Handles common displays such as "$54.99" and "1099 points".
    found = re.search(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?", value)
    if not found:
        return None
    try:
        return Decimal(found.group(0).replace(",", ""))
    except InvalidOperation:
        return None


def add_calendar_months(value: date, months: int) -> date:
    """Return the same day N calendar months later, clamped to month end."""
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def normalized(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def merchant_is_excluded(merchant: Any) -> Optional[str]:
    name = normalized(merchant)
    if not name:
        return None
    # A brand at the beginning is sufficient for common product suffixes,
    # e.g. a vendor name followed by a product tier.
    for brand in EXCLUDED_BRANDS:
        if name == brand or name.startswith(brand + " "):
            return brand
    return None


def is_completed(status: Any) -> bool:
    return normalized(status) in {"completed", "posted"}


def account_open_dates(accounts: Iterable[Dict[str, Any]]) -> Dict[str, date]:
    result: Dict[str, date] = {}
    for account in accounts:
        card_type = account.get("card_type") or account.get("credit_card_type")
        opened = parse_date(account.get("date_of_account_open"))
        if card_type in (BUSINESS, SILVER) and opened:
            result[str(card_type)] = opened
    return result


def expected_reward(transaction: Dict[str, Any], opens: Dict[str, date]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    card = transaction.get("credit_card_type") or transaction.get("card_type")
    if card not in (BUSINESS, SILVER):
        return None, "unsupported_card_type"
    if not is_completed(transaction.get("status")):
        return None, "transaction_not_posted_or_completed"

    amount = parse_decimal(transaction.get("transaction_amount"))
    earned = parse_decimal(transaction.get("rewards_earned"))
    tx_date = parse_date(transaction.get("transaction_date"))
    if amount is None or amount < 0:
        return None, "missing_or_invalid_transaction_amount"
    if earned is None or earned < 0:
        return None, "missing_or_invalid_recorded_rewards"
    if tx_date is None:
        return None, "missing_or_invalid_transaction_date"

    category = normalized(transaction.get("category"))
    bonus_category = category in BONUS_CATEGORIES
    rationale: List[str] = []

    if card == SILVER:
        rate = Decimal("4") if bonus_category else Decimal("1")
        rationale.append("4% posted travel/software category" if bonus_category else "1% non-bonus posted category")
    else:
        excluded = merchant_is_excluded(transaction.get("merchant_name"))
        if bonus_category and not excluded:
            rate = Decimal("10")
            rationale.append("10% eligible posted travel/software category")
        else:
            rate = Decimal("1")
            if excluded:
                rationale.append("1% Business Silver merchant exclusion: " + excluded)
            else:
                rationale.append("1% non-bonus posted category")

        opened = opens.get(BUSINESS)
        if opened is None:
            return None, "missing_business_card_open_date"
        if tx_date < opened:
            return None, "transaction_precedes_business_card_open_date"
        # The first six months is modeled as [opening date, six-month anniversary).
        promo_eligible = (
            PROMO_START <= opened <= PROMO_END
            and opened <= tx_date < add_calendar_months(opened, 6)
        )
        if promo_eligible:
            rate *= Decimal("2")
            rationale.append("2x new-customer Business Silver promotion")
        else:
            rationale.append("no active Business Silver 2x promotion")

    expected = (amount * rate).to_integral_value(rounding=ROUND_FLOOR)
    recorded = earned.to_integral_value(rounding=ROUND_FLOOR)
    difference = expected - recorded
    return {
        "transaction_id": transaction.get("transaction_id"),
        "card_type": card,
        "merchant_name": transaction.get("merchant_name"),
        "transaction_date": transaction.get("transaction_date"),
        "category": transaction.get("category"),
        "transaction_amount": format(amount, "f"),
        "applicable_rate_percent": format(rate, "f"),
        "expected_points": int(expected),
        "recorded_points": int(recorded),
        "point_difference": int(difference),
        "cash_difference": format(abs(difference) / Decimal("100"), ".2f"),
        "rationale": rationale,
    }, None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        json.dump({"error": "invalid_json_input", "detail": str(exc)}, sys.stdout)
        return 2
    if not isinstance(payload, dict):
        json.dump({"error": "input_must_be_object"}, sys.stdout)
        return 2

    accounts = payload.get("accounts", [])
    transactions = payload.get("transactions", [])
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        json.dump({"error": "accounts_and_transactions_must_be_arrays"}, sys.stdout)
        return 2

    opens = account_open_dates(a for a in accounts if isinstance(a, dict))
    audited: List[Dict[str, Any]] = []
    shortfalls: List[Dict[str, Any]] = []
    overawards: List[Dict[str, Any]] = []
    matches: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for transaction in transactions:
        if not isinstance(transaction, dict):
            skipped.append({"transaction_id": None, "reason": "transaction_is_not_object"})
            continue
        finding, reason = expected_reward(transaction, opens)
        if reason:
            skipped.append({"transaction_id": transaction.get("transaction_id"), "reason": reason})
            continue
        assert finding is not None
        audited.append(finding)
        if finding["point_difference"] > 0:
            shortfalls.append(finding)
        elif finding["point_difference"] < 0:
            overawards.append(finding)
        else:
            matches.append(finding)

    output = {
        "audited": audited,
        "shortfalls": shortfalls,
        "overawards": overawards,
        "matches": matches,
        "skipped": skipped,
        "summary": {
            "audited_count": len(audited),
            "shortfall_count": len(shortfalls),
            "overaward_count": len(overawards),
            "match_count": len(matches),
            "skipped_count": len(skipped),
        },
    }
    json.dump(output, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
