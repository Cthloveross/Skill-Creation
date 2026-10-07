#!/usr/bin/env python3
"""Read a reward-audit request from stdin and emit deterministic JSON results.

This helper performs no network, file, or banking operations.
"""
import json
import re
import sys
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

BUSINESS = "Business Silver Rewards Card"
PERSONAL = "Silver Rewards Card"
PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)
EXCLUSIONS = (
    "concur", "sap concur", "expensify", "navan", "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online", "coursera",
    "udemy", "linkedin learning", "skillshare", "pluralsight",
)


def parse_date(value, field_name="date", allow_us_format=True):
    """Parse ISO dates and, for transaction observations, MM/DD/YYYY dates."""
    if not isinstance(value, str):
        raise ValueError(field_name + " must be a date string")
    text = value.strip()
    formats = ("%Y-%m-%d", "%m/%d/%Y") if allow_us_format else ("%Y-%m-%d",)
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    expected = "YYYY-MM-DD or MM/DD/YYYY" if allow_us_format else "YYYY-MM-DD"
    raise ValueError(field_name + " must use " + expected)


def six_month_anniversary(opened):
    month_index = opened.month - 1 + 6
    year = opened.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(opened.day, monthrange(year, month)[1]))


def money(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("amount is missing")
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("amount is not decimal") from exc
    if result < 0:
        raise ValueError("amount must not be negative")
    return result


def points(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("recorded rewards are missing")
    text = str(value).strip().lower().replace(",", "")
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*(?:points?)?", text)
    if not match:
        raise ValueError("recorded rewards must be a numeric point value")
    numeric = Decimal(match.group(1))
    if numeric != numeric.to_integral_value():
        raise ValueError("recorded rewards are not whole points")
    return int(numeric)


def normalized(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def excluded_merchant(name):
    merchant = normalized(name)
    for brand in EXCLUSIONS:
        # Match an exact brand or a brand followed by a normal merchant-name separator.
        if merchant == brand or merchant.startswith(brand + " ") or merchant.startswith(brand + "-"):
            return brand
    return None


def whole_points(amount, rate):
    # dollars * cash-back rate / $.01 per point
    raw = amount * rate * Decimal("100")
    return int(raw.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def account_for(tx, accounts_by_id, accounts_by_type):
    account_id = tx.get("account_id")
    if account_id:
        account = accounts_by_id.get(str(account_id))
        if account is None:
            raise ValueError("transaction account_id is not in accounts")
        return account
    matches = accounts_by_type.get(tx.get("credit_card_type"), [])
    if len(matches) != 1:
        raise ValueError("account_id is required unless card type maps to exactly one account")
    return matches[0]


def calculate(tx, account):
    card_type = tx.get("credit_card_type") or account.get("card_type")
    if card_type != account.get("card_type"):
        raise ValueError("transaction card type does not match account card type")
    if card_type not in (BUSINESS, PERSONAL):
        raise ValueError("unsupported card type")
    status = normalized(tx.get("status"))
    if status not in ("completed", "posted"):
        raise ValueError("transaction is not posted/completed")
    category = normalized(tx.get("category"))
    if category not in ("travel", "software") and not category:
        raise ValueError("transaction category is missing")

    transaction_date = parse_date(tx.get("transaction_date"), "transaction_date")
    amount = money(tx.get("transaction_amount"))
    exclusion = None
    promo_applied = False
    if card_type == PERSONAL:
        rate = Decimal("0.04") if category in ("travel", "software") else Decimal("0.01")
        rationale = "Personal Silver bonus category" if rate == Decimal("0.04") else "Personal Silver base category"
    else:
        exclusion = excluded_merchant(tx.get("merchant_name"))
        rate = Decimal("0.10") if category in ("travel", "software") and not exclusion else Decimal("0.01")
        if exclusion:
            rationale = "Business Silver excluded merchant: " + exclusion
        elif rate == Decimal("0.10"):
            rationale = "Business Silver bonus category"
        else:
            rationale = "Business Silver base category"
        opened = parse_date(account.get("date_of_account_open"), "date_of_account_open", False)
        eligible_opening = PROMO_START <= opened <= PROMO_END
        if eligible_opening and opened <= transaction_date < six_month_anniversary(opened):
            rate *= Decimal("2")
            promo_applied = True
            rationale += "; eligible double-cash-back promotion"

    expected = whole_points(amount, rate)
    recorded = points(tx.get("rewards_earned"))
    return {
        "transaction_id": tx.get("transaction_id"),
        "account_id": account.get("account_id"),
        "card_type": card_type,
        "expected_rewards_points": expected,
        "recorded_rewards_points": recorded,
        "difference_points": expected - recorded,
        "difference_dollars": format(Decimal(expected - recorded) / Decimal("100"), ".2f"),
        "applied_rate_percent": format(rate * Decimal("100"), ".1f"),
        "promotion_applied": promo_applied,
        "excluded_merchant": exclusion,
        "rationale": rationale,
    }


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("top-level JSON must be an object")
    accounts = payload.get("accounts")
    transactions = payload.get("transactions")
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        raise ValueError("accounts and transactions must be arrays")

    accounts_by_id, accounts_by_type, input_errors = {}, {}, []
    for index, account in enumerate(accounts):
        if not isinstance(account, dict):
            input_errors.append({"account_index": index, "reason": "account must be an object"})
            continue
        account_id = account.get("account_id")
        if not account_id:
            input_errors.append({"account_index": index, "reason": "account_id is required"})
            continue
        if str(account_id) in accounts_by_id:
            input_errors.append({"account_index": index, "reason": "duplicate account_id"})
            continue
        accounts_by_id[str(account_id)] = account
        accounts_by_type.setdefault(account.get("card_type"), []).append(account)

    audited, discrepancies, review_required = [], [], []
    for index, tx in enumerate(transactions):
        txid = tx.get("transaction_id") if isinstance(tx, dict) else None
        if not isinstance(tx, dict):
            review_required.append({"transaction_index": index, "transaction_id": txid, "reason": "transaction must be an object"})
            continue
        if not txid:
            review_required.append({"transaction_index": index, "reason": "transaction_id is required"})
            continue
        try:
            result = calculate(tx, account_for(tx, accounts_by_id, accounts_by_type))
            audited.append(result)
            if result["difference_points"] != 0:
                discrepancies.append(result)
        except (ValueError, TypeError) as exc:
            review_required.append({"transaction_id": txid, "reason": str(exc)})

    matching_count = len(audited) - len(discrepancies)
    return {
        "input_errors": input_errors,
        "audited": audited,
        "discrepancies": discrepancies,
        "review_required": review_required,
        "summary": {
            "transactions_supplied": len(transactions),
            "audited_count": len(audited),
            "matching_count": matching_count,
            "discrepancy_count": len(discrepancies),
            "review_required_count": len(review_required),
        },
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), separators=(",", ":"), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(2)
