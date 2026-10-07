#!/usr/bin/env python3
"""Deterministic rewards-review calculator.

Reads a JSON object from stdin and emits a JSON report to stdout.  It does not
contact banking systems and does not modify rewards or accounts.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

BUSINESS = "Business Silver Rewards Card"
SILVER = "Silver Rewards Card"
PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)
BONUS_CATEGORIES = {"travel", "software"}
EXCLUSIONS = (
    "concur", "sap concur", "expensify", "navan",
    "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online",
    "coursera", "udemy", "linkedin learning", "skillshare", "pluralsight",
)


def as_decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a decimal number") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def parse_date(value: Any, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def add_calendar_months(d: date, months: int) -> date:
    """Return the calendar anniversary, clamping days for short months."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    # Last day of destination month without third-party dependencies.
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = (next_month - __import__("datetime").timedelta(days=1)).day
    return date(year, month, min(d.day, last_day))


def merchant_is_excluded(name: Any) -> bool:
    normalized = " ".join(str(name).casefold().split())
    # Exclusions identify merchants; a product descriptor after the merchant
    # name remains excluded. Avoid arbitrary substring matches.
    return any(normalized == item or normalized.startswith(item + " ") for item in EXCLUSIONS)


def money(points: Decimal) -> str:
    return format((points / Decimal("100")).quantize(Decimal("0.01")), ".2f")


def account_map(accounts: list[Any]) -> tuple[dict[str, date], list[str]]:
    result: dict[str, date] = {}
    errors: list[str] = []
    for index, account in enumerate(accounts):
        if not isinstance(account, dict):
            errors.append(f"accounts[{index}] is not an object")
            continue
        card_type = account.get("card_type")
        if card_type not in (SILVER, BUSINESS):
            continue
        try:
            opened = parse_date(account.get("date_of_account_open"), f"accounts[{index}].date_of_account_open")
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if card_type in result:
            errors.append(f"multiple accounts supplied for card type {card_type!r}; transaction-to-account association is ambiguous")
        else:
            result[card_type] = opened
    return result, errors


def review_transaction(tx: dict[str, Any], openings: dict[str, date], silver_base: Decimal) -> dict[str, Any]:
    identifier = tx.get("transaction_id")
    output: dict[str, Any] = {"transaction_id": identifier, "finding": "unreviewed"}
    card = tx.get("credit_card_type")
    if card not in (SILVER, BUSINESS):
        output["reason"] = "Unsupported card type for this skill"
        return output
    if card not in openings:
        output["reason"] = "No unambiguous account opening date was supplied for this card type"
        return output
    if str(tx.get("status", "")).upper() != "COMPLETED":
        output["reason"] = "Transaction is not a completed posted purchase"
        return output
    try:
        amount = as_decimal(tx.get("transaction_amount"), "transaction_amount")
        recorded = as_decimal(tx.get("rewards_earned"), "rewards_earned")
        tx_date = parse_date(tx.get("transaction_date"), "transaction_date")
    except ValueError as exc:
        output["reason"] = str(exc)
        return output
    if amount < 0 or recorded < 0:
        output["reason"] = "Negative amounts or rewards require manual review"
        return output

    category = str(tx.get("category", "")).casefold().strip()
    is_bonus_category = category in BONUS_CATEGORIES
    excluded = card == BUSINESS and merchant_is_excluded(tx.get("merchant_name", ""))
    rationale: list[str] = []
    if card == SILVER:
        rate = Decimal("0.04") if is_bonus_category else silver_base
        rationale.append("Silver Travel/Software rate" if is_bonus_category else "Silver base rate")
    else:
        base_rate = Decimal("0.01")
        rate = Decimal("0.10") if is_bonus_category and not excluded else base_rate
        if excluded:
            rationale.append("Business merchant exclusion: standard rate")
        elif is_bonus_category:
            rationale.append("Business Travel/Software rate")
        else:
            rationale.append("Business standard rate")
        opening = openings[BUSINESS]
        enrolled = PROMO_START <= opening <= PROMO_END
        promo_end = add_calendar_months(opening, 6)
        if enrolled and opening <= tx_date < promo_end:
            rate *= Decimal("2")
            rationale.append("2x new-customer promotion")

    expected = (amount * rate * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    difference = expected - recorded
    if difference > 0:
        finding = "underpaid"
    elif difference < 0:
        finding = "overpaid"
    else:
        finding = "matched"
    output.update({
        "finding": finding,
        "card_type": card,
        "merchant_name": tx.get("merchant_name"),
        "transaction_date": tx.get("transaction_date"),
        "category": tx.get("category"),
        "amount_dollars": format(amount.quantize(Decimal("0.01")), ".2f"),
        "rate_percent": format(rate * Decimal("100"), "f"),
        "expected_points": int(expected),
        "expected_cash_back_dollars": money(expected),
        "recorded_points": int(recorded) if recorded == recorded.to_integral_value() else format(recorded, "f"),
        "recorded_cash_back_dollars": money(recorded),
        "difference_points": int(difference) if difference == difference.to_integral_value() else format(difference, "f"),
        "difference_cash_back_dollars": money(difference),
        "rationale": rationale,
    })
    return output


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object")
        accounts = payload.get("accounts")
        transactions = payload.get("transactions")
        if not isinstance(accounts, list) or not isinstance(transactions, list):
            raise ValueError("accounts and transactions must both be arrays")
        silver_base = as_decimal(payload.get("silver_base_rate", "0.01"), "silver_base_rate")
        if silver_base < 0:
            raise ValueError("silver_base_rate must not be negative")
        openings, errors = account_map(accounts)
        reviews = []
        for index, tx in enumerate(transactions):
            if not isinstance(tx, dict):
                reviews.append({"transaction_id": None, "finding": "unreviewed", "reason": f"transactions[{index}] is not an object"})
            else:
                reviews.append(review_transaction(tx, openings, silver_base))
        counts = {key: sum(r["finding"] == key for r in reviews) for key in ("underpaid", "matched", "overpaid", "unreviewed")}
        report = {
            "review_rules": {
                "point_value_dollars": "0.01",
                "rounding": "half-up to whole points",
                "business_promo_account_open_window": [PROMO_START.isoformat(), PROMO_END.isoformat()],
                "business_promo_transaction_window": "opening date inclusive through six-calendar-month anniversary exclusive",
            },
            "input_errors": errors,
            "summary": {"total_transactions": len(reviews), **counts},
            "reviews": reviews,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
