#!/usr/bin/env python3
"""Analyze supplied card transactions against documented rewards rules.

Reads one JSON object from stdin and writes one JSON report to stdout.  This
program is read-only and has no banking-tool integration.
"""
import calendar
import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

BUSINESS = "Business Silver Rewards Card"
SILVER = "Silver Rewards Card"
PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)
EXCLUSIONS = (
    "concur", "sap concur", "expensify", "navan", "apple", "microsoft",
    "dell", "xbox game pass", "playstation plus", "nintendo switch online",
    "coursera", "udemy", "linkedin learning", "skillshare", "pluralsight",
)
POSTED_STATUSES = {"COMPLETED", "POSTED"}


def parse_date(value):
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError("date must be YYYY-MM-DD")
    return date.fromisoformat(value.strip()[:10])


def add_calendar_months(start, months):
    """Add calendar months while clamping the day to the target month."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def parse_decimal(value, label):
    if isinstance(value, bool) or value is None:
        raise ValueError(label + " is missing")
    text = str(value).strip().replace(",", "").replace("$", "")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        raise ValueError(label + " is not numeric")
    try:
        return Decimal(match.group(0))
    except InvalidOperation as exc:
        raise ValueError(label + " is not numeric") from exc


def whole_points(amount_dollars, rate):
    # One point is one cent of cash back: dollars * 100 cents * percentage.
    raw = amount_dollars * Decimal("100") * rate
    return int(raw.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def merchant_is_excluded(merchant):
    normalized = str(merchant or "").casefold()
    return any(item in normalized for item in EXCLUSIONS)


def is_bonus_category(category):
    return str(category or "").strip().casefold() in {"travel", "software"}


def find_account(card_type, accounts):
    matches = [a for a in accounts if a.get("card_type") == card_type]
    if len(matches) == 1:
        return matches[0], None
    if not matches:
        return None, "no matching account supplied for card type"
    return None, "multiple matching accounts; transaction lacks account identifier"


def business_rate(account, transaction, tx_date):
    try:
        opened = parse_date(account.get("date_of_account_open"))
    except Exception:
        return None, "Business Silver account opening date is missing or invalid"
    qualifying = is_bonus_category(transaction.get("category"))
    excluded = merchant_is_excluded(transaction.get("merchant_name"))
    base = Decimal("0.10") if qualifying and not excluded else Decimal("0.01")
    promo_eligible = PROMO_START <= opened <= PROMO_END
    promo_active = promo_eligible and opened <= tx_date < add_calendar_months(opened, 6)
    rate = base * (2 if promo_active else 1)
    if excluded:
        reason = "named merchant exclusion uses the standard rate"
    elif qualifying:
        reason = "coded Travel/Software category qualifies for the enhanced rate"
    else:
        reason = "non-Travel/Software coded category uses the standard rate"
    if promo_active:
        reason += "; eligible new-customer promotion doubles that rate"
    elif promo_eligible:
        reason += "; transaction is outside the first six calendar months"
    else:
        reason += "; no eligible new-customer promotion"
    return rate, reason


def silver_rate(transaction):
    qualifying = is_bonus_category(transaction.get("category"))
    rate = Decimal("0.04") if qualifying else Decimal("0.01")
    reason = ("coded Travel/Software category qualifies for the 4% rate"
              if qualifying else "non-Travel/Software coded category uses the 1% rate")
    return rate, reason


def analyze(payload):
    accounts = payload.get("accounts")
    transactions = payload.get("transactions")
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        raise ValueError("accounts and transactions must both be arrays")

    report = {
        "as_of": payload.get("as_of"),
        "analyses": [],
        "discrepancies": [],
        "skipped": [],
        "warnings": [],
        "totals": {"expected_points": 0, "recorded_points": 0,
                   "apparent_undercredit_points": 0, "apparent_overcredit_points": 0},
    }
    for tx in transactions:
        tx_id = tx.get("transaction_id") or "(missing transaction_id)"
        status = str(tx.get("status") or "").upper()
        if status not in POSTED_STATUSES:
            report["skipped"].append({"transaction_id": tx_id, "reason": "transaction is not completed/posted"})
            continue
        card_type = tx.get("credit_card_type")
        if card_type not in {BUSINESS, SILVER}:
            report["skipped"].append({"transaction_id": tx_id, "reason": "unsupported card type"})
            continue
        account, account_error = find_account(card_type, accounts)
        if account_error:
            report["skipped"].append({"transaction_id": tx_id, "reason": account_error})
            continue
        try:
            tx_date = parse_date(tx.get("transaction_date"))
            amount = parse_decimal(tx.get("transaction_amount"), "transaction_amount")
            recorded = int(parse_decimal(tx.get("rewards_earned"), "rewards_earned").quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            if amount < 0 or recorded < 0:
                raise ValueError("negative transaction amount or rewards are unsupported")
            if card_type == BUSINESS:
                rate, basis = business_rate(account, tx, tx_date)
                if rate is None:
                    raise ValueError(basis)
            else:
                rate, basis = silver_rate(tx)
            expected = whole_points(amount, rate)
        except (ValueError, InvalidOperation) as exc:
            report["skipped"].append({"transaction_id": tx_id, "reason": str(exc)})
            continue

        difference = expected - recorded
        item = {
            "transaction_id": tx_id,
            "card_type": card_type,
            "transaction_date": tx_date.isoformat(),
            "merchant_name": tx.get("merchant_name"),
            "category": tx.get("category"),
            "amount_dollars": format(amount, "f"),
            "expected_rate_percent": format(rate * Decimal("100"), "f"),
            "expected_points": expected,
            "recorded_points": recorded,
            "difference_points": difference,
            "basis": basis,
        }
        report["analyses"].append(item)
        report["totals"]["expected_points"] += expected
        report["totals"]["recorded_points"] += recorded
        if difference != 0:
            report["discrepancies"].append(item)
            if difference > 0:
                report["totals"]["apparent_undercredit_points"] += difference
            else:
                report["totals"]["apparent_overcredit_points"] += -difference
    return report


def main():
    try:
        payload = json.load(sys.stdin)
        result = analyze(payload)
        print(json.dumps(result, separators=(",", ":"), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(2)


if __name__ == "__main__":
    main()
