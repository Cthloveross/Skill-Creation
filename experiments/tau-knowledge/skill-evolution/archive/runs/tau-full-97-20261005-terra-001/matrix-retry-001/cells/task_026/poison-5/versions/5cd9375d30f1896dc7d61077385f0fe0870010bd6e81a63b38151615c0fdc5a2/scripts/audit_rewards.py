#!/usr/bin/env python3
"""Calculate expected cash-back points for Silver and Business Silver transactions.

Reads one JSON object from stdin and emits one JSON object on stdout. This helper
makes no network calls and performs no banking action.
"""
import calendar
import json
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

BUSINESS = "Business Silver Rewards Card"
SILVER = "Silver Rewards Card"
PROMO_START = datetime(2024, 11, 14).date()
PROMO_END = datetime(2025, 11, 14).date()
QUALIFYING_CATEGORIES = {"travel", "software", "saas", "software/saas"}
EXCLUDED_MERCHANTS = (
    "concur", "sap concur", "expensify", "navan", "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online", "coursera",
    "udemy", "linkedin learning", "skillshare", "pluralsight",
)


def normalized(value):
    return " ".join(str(value or "").casefold().split())


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be YYYY-MM-DD or MM/DD/YYYY")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"{field} must be YYYY-MM-DD or MM/DD/YYYY")


def decimal_value(value, field, allow_points_suffix=False):
    text = str(value).strip().replace("$", "").replace(",", "")
    if allow_points_suffix:
        text = re.sub(r"\s*points?\s*$", "", text, flags=re.IGNORECASE)
    try:
        result = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def add_calendar_months(start, months):
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return start.replace(year=year, month=month, day=day)


def matches_exclusion(merchant):
    merchant = normalized(merchant)
    for excluded in EXCLUDED_MERCHANTS:
        if merchant == excluded or merchant.startswith(excluded + " "):
            return excluded
    return None


def account_for_transaction(transaction, accounts):
    account_id = transaction.get("account_id")
    if account_id is not None:
        matches = [a for a in accounts if a.get("account_id") == account_id]
        if len(matches) == 1:
            return matches[0], None
        return None, "account_id did not match exactly one supplied account"
    matches = [a for a in accounts if a.get("card_type") == transaction.get("credit_card_type")]
    if len(matches) == 1:
        return matches[0], None
    if not matches:
        return None, "no supplied account matched credit_card_type"
    return None, "multiple supplied accounts match credit_card_type; account_id is required"


def expected_rate(account, transaction_date, category, merchant, end_inclusive):
    card_type = account.get("card_type")
    qualifying = normalized(category) in QUALIFYING_CATEGORIES
    if card_type == SILVER:
        return (Decimal("4.0") if qualifying else Decimal("1.0"),
                "Silver Rewards Card category rate")
    if card_type != BUSINESS:
        return None, "unsupported card type"

    exclusion = matches_exclusion(merchant) if qualifying else None
    base = Decimal("1.0") if not qualifying or exclusion else Decimal("10.0")
    if qualifying and not exclusion:
        basis = "Business Silver qualifying Travel/Software rate"
    elif exclusion:
        basis = f"Business Silver published exclusion matched: {exclusion}"
    else:
        basis = "Business Silver other-purchase rate"

    opened = parse_date(account.get("date_of_account_open"), "date_of_account_open")
    offer_eligible = PROMO_START <= opened <= PROMO_END
    anniversary = add_calendar_months(opened, 6)
    in_window = transaction_date <= anniversary if end_inclusive else transaction_date < anniversary
    if offer_eligible and in_window:
        return base * 2, basis + "; eligible double-cash-back period"
    return base, basis


def points_number(value):
    if value != value.to_integral_value():
        raise ValueError("rewards_earned must be a whole number of points")
    return int(value)


def money_number(points):
    return float((Decimal(points) / 100).quantize(Decimal("0.01")))


def evaluate(transaction, accounts, end_inclusive):
    output = {
        "transaction_id": transaction.get("transaction_id"),
        "merchant_name": transaction.get("merchant_name"),
        "outcome": "not_evaluated",
    }
    account, error = account_for_transaction(transaction, accounts)
    if error:
        output["reason"] = error
        return output
    output.update({"account_id": account.get("account_id"), "card_type": account.get("card_type")})

    if normalized(transaction.get("status")) not in {"completed", "posted"}:
        output["reason"] = "transaction is not posted/completed"
        return output
    category = transaction.get("category")
    if not isinstance(category, str) or not category.strip():
        output["reason"] = "posted merchant category is missing"
        return output

    try:
        amount = decimal_value(transaction.get("transaction_amount"), "transaction_amount")
        recorded = points_number(decimal_value(transaction.get("rewards_earned"), "rewards_earned", True))
        transaction_date = parse_date(transaction.get("transaction_date"), "transaction_date")
    except ValueError as exc:
        output["reason"] = str(exc)
        return output
    if amount <= 0:
        output["reason"] = "transaction amount is not a positive purchase"
        return output
    if recorded < 0:
        output["reason"] = "recorded rewards are negative and require reversal review"
        return output

    try:
        rate, basis = expected_rate(account, transaction_date, category,
                                    transaction.get("merchant_name"), end_inclusive)
    except ValueError as exc:
        output["reason"] = str(exc)
        return output
    if rate is None:
        output["reason"] = basis
        return output

    expected = int((amount * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    difference = expected - recorded
    output.update({
        "transaction_date": transaction.get("transaction_date"),
        "transaction_amount": str(amount.quantize(Decimal("0.01"))),
        "category": category,
        "recorded_points": recorded,
        "expected_points": expected,
        "expected_rate_percent": float(rate),
        "calculation_basis": basis,
        "shortfall_points": 0,
        "shortfall_cash_back": 0.0,
        "excess_points": 0,
        "excess_cash_back": 0.0,
    })
    if difference == 0:
        output["outcome"] = "match"
    elif difference > 0:
        output.update({
            "outcome": "under_earned",
            "shortfall_points": difference,
            "shortfall_cash_back": money_number(difference),
        })
    else:
        excess = -difference
        output.update({
            "outcome": "over_earned",
            "excess_points": excess,
            "excess_cash_back": money_number(excess),
        })
    return output


def audit(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    accounts, transactions = payload.get("accounts"), payload.get("transactions")
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        raise ValueError("accounts and transactions must both be arrays")
    if not all(isinstance(item, dict) for item in accounts + transactions):
        raise ValueError("accounts and transactions entries must be objects")
    end_inclusive = payload.get("promo_end_inclusive", False)
    if not isinstance(end_inclusive, bool):
        raise ValueError("promo_end_inclusive must be boolean")

    results = [evaluate(transaction, accounts, end_inclusive) for transaction in transactions]
    total_shortfall = sum(row.get("shortfall_points", 0) for row in results)
    total_excess = sum(row.get("excess_points", 0) for row in results)
    return {
        "results": results,
        "summary": {
            "transactions_received": len(transactions),
            "results_produced": len(results),
            "outcomes": {
                key: sum(row["outcome"] == key for row in results)
                for key in ("match", "under_earned", "over_earned", "not_evaluated")
            },
            "total_shortfall_points": total_shortfall,
            "total_shortfall_cash_back": money_number(total_shortfall),
            "total_excess_points": total_excess,
            "total_excess_cash_back": money_number(total_excess),
            "point_cash_back_value": "$0.01",
        },
    }


def main():
    try:
        print(json.dumps(audit(json.load(sys.stdin)), separators=(",", ":"), sort_keys=True))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}))


if __name__ == "__main__":
    main()
