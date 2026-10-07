#!/usr/bin/env python3
"""Read reward-audit input JSON from stdin and write a JSON audit report to stdout."""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

BUSINESS = "business silver rewards card"
SILVER = "silver rewards card"
PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)
EXACT_EXCLUSIONS = {
    "concur", "sap concur", "expensify", "navan", "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online", "coursera",
    "udemy", "linkedin learning", "skillshare", "pluralsight",
}
# A branded merchant descriptor (for example, a product or subscription name) is still
# the named excluded merchant. Prefix matching is deliberately limited to these brands.
EXCLUSION_PREFIXES = ("concur ", "sap concur ", "apple ", "microsoft ", "dell ")


def parse_date(value):
    return date.fromisoformat(str(value))


def add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    month_lengths = (31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                     31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    return date(year, month, min(value.day, month_lengths[month - 1]))


def norm(value):
    return " ".join(str(value or "").casefold().split())


def is_business_exclusion(merchant):
    name = norm(merchant)
    return name in EXACT_EXCLUSIONS or name.startswith(EXCLUSION_PREFIXES)


def point_value(amount, rate):
    # One point is one cent, so dollars * percent * 100 produces points.
    return int((amount * rate * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def promo_active(opened, txn_date):
    if not (PROMO_START <= opened <= PROMO_END):
        return False
    return opened <= txn_date < add_months(opened, 6)


def account_index(accounts):
    result = {}
    errors = []
    for i, account in enumerate(accounts):
        card = norm(account.get("card_type"))
        try:
            opened = parse_date(account["date_of_account_open"])
        except (KeyError, TypeError, ValueError):
            errors.append({"kind": "account", "index": i, "error": "invalid_or_missing_date_of_account_open"})
            continue
        if card in result:
            errors.append({"kind": "account", "index": i, "error": "duplicate_card_type"})
            continue
        result[card] = opened
    return result, errors


def audit_one(txn, opened_by_card):
    row = {"transaction_id": txn.get("transaction_id"), "card_type": txn.get("credit_card_type"),
           "merchant_name": txn.get("merchant_name"), "transaction_date": txn.get("transaction_date")}
    card = norm(txn.get("credit_card_type"))
    if norm(txn.get("status")) != "completed":
        row.update(outcome="not_auditable", reason="transaction_not_completed")
        return row
    if card not in (BUSINESS, SILVER):
        row.update(outcome="not_auditable", reason="unsupported_card_type")
        return row
    if card not in opened_by_card:
        row.update(outcome="not_auditable", reason="no_valid_matching_account")
        return row
    try:
        amount = Decimal(str(txn["transaction_amount"]))
        txn_date = parse_date(txn["transaction_date"])
        recorded = int(txn["rewards_earned"])
        if amount < 0 or recorded < 0:
            raise ValueError
    except (KeyError, TypeError, ValueError, InvalidOperation):
        row.update(outcome="not_auditable", reason="invalid_amount_date_or_recorded_points")
        return row

    qualifying_category = norm(txn.get("category")) in {"travel", "software"}
    reason = "standard_category"
    if card == SILVER:
        rate = Decimal("0.04") if qualifying_category else Decimal("0.01")
        if qualifying_category:
            reason = "silver_travel_or_software_category"
    else:
        promo = promo_active(opened_by_card[card], txn_date)
        if is_business_exclusion(txn.get("merchant_name")):
            rate = Decimal("0.01")
            reason = "business_documented_merchant_exclusion"
        elif qualifying_category:
            rate = Decimal("0.10")
            reason = "business_travel_or_software_category"
        else:
            rate = Decimal("0.01")
        if promo:
            rate *= 2
            reason += "_double_cash_back_promo"

    expected = point_value(amount, rate)
    difference = expected - recorded
    row.update({
        "outcome": "match" if difference == 0 else "discrepancy",
        "reason": reason,
        "amount": format(amount.quantize(Decimal("0.01")), "f"),
        "category": txn.get("category"),
        "expected_rate_percent": format(rate * 100, "f"),
        "expected_points": expected,
        "recorded_points": recorded,
        "difference_points": difference,
        "difference_cash": format((Decimal(difference) / 100).quantize(Decimal("0.01")), "f"),
    })
    return row


def main():
    try:
        payload = json.load(sys.stdin)
        accounts = payload["accounts"]
        transactions = payload["transactions"]
        if not isinstance(accounts, list) or not isinstance(transactions, list):
            raise ValueError("accounts_and_transactions_must_be_lists")
    except Exception as exc:
        print(json.dumps({"error": "invalid_input", "detail": str(exc)}))
        return

    opened_by_card, input_errors = account_index(accounts)
    audited = [audit_one(txn, opened_by_card) if isinstance(txn, dict) else
               {"outcome": "not_auditable", "reason": "transaction_is_not_an_object"}
               for txn in transactions]
    discrepancies = [row for row in audited if row.get("outcome") == "discrepancy"]
    report = {
        "as_of_date": payload.get("as_of_date"),
        "audited": audited,
        "input_errors": input_errors,
        "summary": {
            "transactions_received": len(transactions),
            "matches": sum(r.get("outcome") == "match" for r in audited),
            "discrepancies": len(discrepancies),
            "not_auditable": sum(r.get("outcome") == "not_auditable" for r in audited),
            "total_positive_shortfall_points": sum(max(0, r["difference_points"]) for r in discrepancies),
            "total_apparent_overcredit_points": sum(max(0, -r["difference_points"]) for r in discrepancies),
        },
    }
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
