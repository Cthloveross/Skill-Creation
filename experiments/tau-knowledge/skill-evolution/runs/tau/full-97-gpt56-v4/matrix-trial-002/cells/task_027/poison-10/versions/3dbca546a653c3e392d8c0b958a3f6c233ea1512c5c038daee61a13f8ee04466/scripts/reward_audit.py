#!/usr/bin/env python3
"""Calculate supportable expected cash-back points from supplied card records.

Input and output are JSON objects on stdin/stdout. This program is read-only and
never performs banking actions.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

BUSINESS = "Business Silver Rewards Card"
SILVER = "Silver Rewards Card"
BONUS_CATEGORIES = {"travel", "software"}
EXCLUSIONS = {
    "concur", "sap concur", "expensify", "navan", "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online", "coursera",
    "udemy", "linkedin learning", "skillshare", "pluralsight",
}
PROMO_OPEN_START = date(2024, 11, 14)
PROMO_OPEN_END = date(2025, 11, 14)


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be YYYY-MM-DD")
    return date.fromisoformat(value)


def money(value):
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    if not isinstance(value, str):
        raise ValueError("amount must be a number or string")
    cleaned = value.strip().replace("$", "").replace(",", "")
    return Decimal(cleaned)


def norm(value):
    return " ".join(str(value or "").strip().casefold().split())


def add_months(d, months):
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    # Determine the last valid day of target month without external libraries.
    for day_num in range(d.day, 0, -1):
        try:
            return date(year, month, day_num)
        except ValueError:
            pass
    raise ValueError("could not calculate anniversary")


def excluded_business_merchant(merchant_name):
    """Return whether a merchant is the named excluded merchant or its labeled service.

    Transaction exports may include a product after the merchant name (for example,
    ``Microsoft 365``). A prefix only counts when it ends at a word boundary, so an
    unrelated name such as ``Applebee`` is not treated as Apple.
    """
    merchant = norm(merchant_name)
    for excluded in EXCLUSIONS:
        if merchant == excluded:
            return True
        if merchant.startswith(excluded):
            remainder = merchant[len(excluded):]
            if remainder and not remainder[0].isalnum():
                return True
    return False


def account_index(accounts):
    result = {}
    for acct in accounts:
        if not isinstance(acct, dict):
            continue
        card_type = acct.get("card_type")
        opened = acct.get("date_of_account_open")
        if card_type in (BUSINESS, SILVER) and opened:
            try:
                result[card_type] = parse_date(opened)
            except ValueError:
                pass
    return result


def calc_transaction(txn, openings):
    out = {
        "transaction_id": txn.get("transaction_id"),
        "card_type": txn.get("credit_card_type"),
        "merchant_name": txn.get("merchant_name"),
        "category": txn.get("category"),
        "status": txn.get("status"),
        "recorded_points": txn.get("rewards_earned"),
    }
    card = txn.get("credit_card_type")
    if card not in (BUSINESS, SILVER):
        out.update(outcome="manual_review", reason="Unsupported card product")
        return out
    if norm(txn.get("status")) != "completed":
        out.update(outcome="manual_review", reason="Only COMPLETED transactions can be audited")
        return out
    try:
        amount = money(txn.get("transaction_amount"))
        tx_date = parse_date(txn.get("transaction_date"))
        recorded = Decimal(str(txn.get("rewards_earned")))
        if recorded != recorded.to_integral_value():
            raise ValueError("recorded rewards must be whole points")
    except (ValueError, InvalidOperation):
        out.update(outcome="manual_review", reason="Missing or invalid amount, date, or whole-point recorded rewards")
        return out
    if amount < 0 or recorded < 0:
        out.update(outcome="manual_review", reason="Negative transaction or reward amount requires review")
        return out

    category_is_bonus = norm(txn.get("category")) in BONUS_CATEGORIES
    excluded = excluded_business_merchant(txn.get("merchant_name"))
    rate = None
    reason = ""
    promo_applied = False

    if card == BUSINESS:
        opened = openings.get(BUSINESS)
        if not opened:
            out.update(outcome="manual_review", reason="Business account opening date is required")
            return out
        in_promo = (PROMO_OPEN_START <= opened <= PROMO_OPEN_END and
                    opened <= tx_date < add_months(opened, 6))
        base_rate = Decimal("0.10") if category_is_bonus and not excluded else Decimal("0.01")
        rate = base_rate * (2 if in_promo else 1)
        promo_applied = in_promo
        if excluded:
            reason = "Merchant is a Business Silver bonus exclusion; standard rate applies"
        elif category_is_bonus:
            reason = "Posted Travel/Software category qualifies for Business Silver bonus rate"
        else:
            reason = "Non-bonus category uses Business Silver standard rate"
    else:
        if not category_is_bonus:
            out.update(
                outcome="indeterminate",
                reason="Available Silver Rewards terms do not state a numeric non-bonus base rate",
                expected_points=None,
                expected_cash_back_dollars=None,
                difference_points=None,
                difference_cash_back_dollars=None,
            )
            return out
        rate = Decimal("0.04")
        reason = "Posted Travel/Software category qualifies for Silver 4% rate"

    expected = (amount * rate * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    difference = expected - recorded
    out.update(
        rate_percent=str(rate * 100),
        promotion_applied=promo_applied,
        expected_points=int(expected),
        expected_cash_back_dollars=format((expected / Decimal("100")).quantize(Decimal("0.01")), ".2f"),
        difference_points=int(difference),
        difference_cash_back_dollars=format((difference / Decimal("100")).quantize(Decimal("0.01")), ".2f"),
        reason=reason,
        outcome="matches_expected" if difference == 0 else "confirmed_mismatch",
    )
    return out


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        accounts = payload.get("accounts", [])
        transactions = payload.get("transactions", [])
        if not isinstance(accounts, list) or not isinstance(transactions, list):
            raise ValueError("accounts and transactions must be arrays")
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"transactions": [], "summary": {}, "input_errors": [str(exc)]}))
        return

    openings = account_index(accounts)
    results, errors = [], []
    for index, txn in enumerate(transactions):
        if not isinstance(txn, dict):
            errors.append("transactions[%d] is not an object" % index)
            continue
        results.append(calc_transaction(txn, openings))

    summary = {"matches_expected": 0, "confirmed_mismatch": 0, "indeterminate": 0, "manual_review": 0}
    for item in results:
        summary[item["outcome"]] = summary.get(item["outcome"], 0) + 1
    print(json.dumps({"transactions": results, "summary": summary, "input_errors": errors}, indent=2))


if __name__ == "__main__":
    main()
