#!/usr/bin/env python3
"""Calculate expected per-transaction cash-back points for supported Silver cards.

Input is a JSON object on stdin:
{
  "accounts": [{"card_type": str, "date_of_account_open": "YYYY-MM-DD"}],
  "transactions": [{"transaction_id": str, "credit_card_type": str,
     "merchant_name": str, "transaction_amount": number|string,
     "transaction_date": "YYYY-MM-DD", "category": str,
     "status": str, "rewards_earned": number|string}]
}

Output is JSON containing reviews, discrepancies, not_reviewed, and validation.
No banking calls or updates are made by this script.
"""
import calendar
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

BUSINESS = "Business Silver Rewards Card"
SILVER = "Silver Rewards Card"
PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)  # Account opening date is inclusive.

# These are the specifically published Business Silver exclusion merchant brands.
EXCLUDED_BRANDS = (
    "concur", "sap concur", "expensify", "navan",
    "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online",
    "coursera", "udemy", "linkedin learning", "skillshare", "pluralsight",
)


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a YYYY-MM-DD string")
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("date must begin with YYYY-MM-DD") from exc


def add_months(d, months):
    month_number = d.month - 1 + months
    year = d.year + month_number // 12
    month = month_number % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def parse_amount(value):
    if isinstance(value, bool):
        raise ValueError("amount must not be boolean")
    if isinstance(value, (int, float, Decimal)):
        candidate = str(value)
    elif isinstance(value, str):
        candidate = value.strip().replace("$", "").replace(",", "")
    else:
        raise ValueError("amount must be numeric or a dollar-formatted string")
    try:
        amount = Decimal(candidate)
    except InvalidOperation as exc:
        raise ValueError("invalid amount") from exc
    if amount < 0:
        raise ValueError("amount must not be negative")
    return amount


def parse_points(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("rewards_earned must not be boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    if isinstance(value, str):
        found = re.fullmatch(r"\s*(-?\d+)\s*(?:points?)?\s*", value, re.I)
        if found:
            return int(found.group(1))
    raise ValueError("rewards_earned must be a whole number or '<whole> points'")


def normalized(value):
    return " ".join(str(value or "").casefold().split())


def is_eligible_category(transaction):
    # An explicit boolean from a trusted merchant-category review takes precedence.
    explicit = transaction.get("qualifying_category")
    if isinstance(explicit, bool):
        return explicit
    category = normalized(transaction.get("category"))
    return category in {"travel", "software", "saas", "software/saas", "software / saas"}


def excluded_business_merchant(merchant):
    name = normalized(merchant)
    # Brand-prefix matching supports provider descriptors such as a product name
    # following the named excluded brand without treating unrelated embedded words
    # as exclusions.
    return any(name == brand or name.startswith(brand + " ") for brand in EXCLUDED_BRANDS)


def rate_and_reason(card_type, account_open, tx_date, eligible, merchant):
    if card_type == BUSINESS:
        excluded = excluded_business_merchant(merchant)
        base_percent = Decimal("10") if eligible and not excluded else Decimal("1")
        reasons = []
        if eligible and not excluded:
            reasons.append("eligible travel/software category at Business Silver bonus rate")
        elif excluded:
            reasons.append("named Business Silver exclusion uses the standard rate")
        else:
            reasons.append("non-qualifying or unconfirmed category uses the standard rate")
        promo = PROMO_START <= account_open <= PROMO_END and account_open <= tx_date < add_months(account_open, 6)
        if promo:
            base_percent *= Decimal("2")
            reasons.append("Business Silver new-account double-cash-back promotion applied")
        return base_percent, "; ".join(reasons)
    if card_type == SILVER:
        rate = Decimal("4") if eligible else Decimal("1")
        reason = "eligible travel/software category at Silver bonus rate" if eligible else "non-qualifying or unconfirmed category uses the standard rate"
        return rate, reason
    raise ValueError("unsupported card type")


def points_for(amount, percent):
    # percent cash back => amount * percent cash dollars => times 100 points/dollar.
    raw = amount * percent
    return int(raw.to_integral_value(rounding=ROUND_FLOOR))


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    accounts = payload.get("accounts")
    transactions = payload.get("transactions")
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        raise ValueError("accounts and transactions must be arrays")

    openings = {}
    account_errors = []
    for index, account in enumerate(accounts):
        if not isinstance(account, dict):
            account_errors.append({"account_index": index, "reason": "account is not an object"})
            continue
        card_type = account.get("card_type")
        if card_type not in (BUSINESS, SILVER):
            continue
        try:
            opening = parse_date(account.get("date_of_account_open"))
        except ValueError as exc:
            account_errors.append({"account_index": index, "card_type": card_type, "reason": str(exc)})
            continue
        # Multiple same-type accounts cannot be safely matched without account_id on transactions.
        if card_type in openings and openings[card_type] != opening:
            account_errors.append({"card_type": card_type, "reason": "multiple different opening dates for the same card type"})
        else:
            openings[card_type] = opening

    reviews, skipped, seen_ids = [], [], set()
    validation_errors = list(account_errors)
    for index, tx in enumerate(transactions):
        if not isinstance(tx, dict):
            skipped.append({"transaction_index": index, "reason": "transaction is not an object"})
            continue
        txid = tx.get("transaction_id")
        if not isinstance(txid, str) or not txid.strip():
            skipped.append({"transaction_index": index, "reason": "missing transaction_id"})
            continue
        if txid in seen_ids:
            skipped.append({"transaction_id": txid, "reason": "duplicate transaction_id"})
            validation_errors.append({"transaction_id": txid, "reason": "duplicate transaction_id"})
            continue
        seen_ids.add(txid)
        status = normalized(tx.get("status"))
        if status not in {"completed", "posted"}:
            skipped.append({"transaction_id": txid, "reason": "transaction is not posted/completed", "status": tx.get("status")})
            continue
        card_type = tx.get("credit_card_type")
        if card_type not in (BUSINESS, SILVER):
            skipped.append({"transaction_id": txid, "reason": "unsupported card type", "card_type": card_type})
            continue
        if card_type not in openings:
            skipped.append({"transaction_id": txid, "reason": "no usable account opening date for card type"})
            continue
        try:
            amount = parse_amount(tx.get("transaction_amount"))
            tx_date = parse_date(tx.get("transaction_date"))
            recorded = parse_points(tx.get("rewards_earned"))
            if tx_date < openings[card_type]:
                raise ValueError("transaction predates account opening")
            eligible = is_eligible_category(tx)
            percent, rationale = rate_and_reason(card_type, openings[card_type], tx_date, eligible, tx.get("merchant_name"))
            expected = points_for(amount, percent)
        except ValueError as exc:
            skipped.append({"transaction_id": txid, "reason": str(exc)})
            continue
        review = {
            "transaction_id": txid,
            "card_type": card_type,
            "merchant_name": tx.get("merchant_name"),
            "transaction_date": tx_date.isoformat(),
            "amount": format(amount, "f"),
            "eligible_category": eligible,
            "rate_percent": format(percent, "f"),
            "expected_points": expected,
            "expected_cash_back_dollars": format(Decimal(expected) / Decimal("100"), ".2f"),
            "recorded_points": recorded,
            "rationale": rationale,
        }
        if recorded is not None:
            review["difference_points"] = expected - recorded
            review["difference_cash_back_dollars"] = format(Decimal(expected - recorded) / Decimal("100"), ".2f")
        reviews.append(review)

    discrepancies = [r for r in reviews if r["recorded_points"] is not None and r["difference_points"] != 0]
    validation = {
        "errors": validation_errors,
        "reviewed_transaction_ids_unique": len({r["transaction_id"] for r in reviews}) == len(reviews),
        "all_expected_points_are_whole_nonnegative": all(isinstance(r["expected_points"], int) and r["expected_points"] >= 0 for r in reviews),
        "reviewed_count": len(reviews),
        "not_reviewed_count": len(skipped),
    }
    return {"reviews": reviews, "discrepancies": discrepancies, "not_reviewed": skipped, "validation": validation}


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        print(json.dumps(main(raw), separators=(",", ":"), ensure_ascii=False))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": {"message": str(exc)}}))
