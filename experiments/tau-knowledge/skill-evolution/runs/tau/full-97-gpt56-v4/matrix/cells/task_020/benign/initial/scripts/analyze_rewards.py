#!/usr/bin/env python3
"""Analyze documented Silver and Business Silver cash-back transaction rewards.
Reads the JSON schema described in SKILL.md from stdin and writes JSON to stdout.
"""
import calendar
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

SILVER = "Silver Rewards Card"
BUSINESS = "Business Silver Rewards Card"
PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)
EXCLUSIONS = (
    "concur", "sap concur", "expensify", "navan", "apple", "microsoft",
    "dell", "xbox game pass", "playstation plus", "nintendo switch online",
    "coursera", "udemy", "linkedin learning", "skillshare", "pluralsight",
)


def parse_date(value):
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def decimal_value(value):
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    if not cleaned:
        raise InvalidOperation
    return Decimal(cleaned)


def points_value(value):
    return int(decimal_value(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def norm(value):
    return " ".join(str(value or "").lower().split())


def merchant_is_excluded(merchant):
    name = norm(merchant)
    return any(term in name for term in EXCLUSIONS)


def eligible_category(category):
    return norm(category) in {"travel", "software", "saas"}


def match_account(transaction, accounts):
    account_id = transaction.get("account_id")
    if account_id:
        matches = [a for a in accounts if str(a.get("account_id")) == str(account_id)]
    else:
        card = transaction.get("credit_card_type")
        matches = [a for a in accounts if a.get("card_type") == card]
    return matches[0] if len(matches) == 1 else None


def rate_and_reason(account, transaction):
    card = account.get("card_type")
    category_bonus = eligible_category(transaction.get("category"))
    if card == SILVER:
        return (Decimal("0.04") if category_bonus else Decimal("0.01"),
                "Silver travel/software rate" if category_bonus else "Silver standard rate", False)
    if card != BUSINESS:
        return None

    excluded = merchant_is_excluded(transaction.get("merchant_name"))
    base = Decimal("0.01") if excluded or not category_bonus else Decimal("0.10")
    reason = "Business standard rate"
    if excluded:
        reason = "Business named merchant exclusion"
    elif category_bonus:
        reason = "Business travel/software rate"

    opened = parse_date(account["date_of_account_open"])
    occurred = parse_date(transaction["transaction_date"])
    eligible_opening = PROMO_START <= opened <= PROMO_END
    # The first-six-month window ends at the matching calendar date six months later.
    # A transaction on that end date is treated as in-window; adjust only if program
    # operations provide a more specific timestamp rule.
    promo_last_day = min(add_months(opened, 6), PROMO_END)
    promo = eligible_opening and opened <= occurred <= promo_last_day
    if promo:
        return base * 2, reason + " (double-cash-back promotion)", True
    return base, reason, False


def analyze(payload):
    accounts = payload.get("accounts")
    transactions = payload.get("transactions")
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        raise ValueError("accounts and transactions must both be arrays")

    findings = []
    for txn in transactions:
        finding = {
            "transaction_id": txn.get("transaction_id"),
            "merchant_name": txn.get("merchant_name"),
            "transaction_date": txn.get("transaction_date"),
            "card_type": txn.get("credit_card_type"),
        }
        if norm(txn.get("status")) != "completed":
            finding.update(status="unreviewable", reason="Only COMPLETED purchases are evaluated.")
            findings.append(finding)
            continue
        account = match_account(txn, accounts)
        if not account:
            finding.update(status="unreviewable", reason="Could not uniquely match transaction to a supplied account.")
            findings.append(finding)
            continue
        try:
            rate_data = rate_and_reason(account, txn)
            if rate_data is None:
                raise ValueError("Unsupported card type")
            rate, reason, promo = rate_data
            amount = decimal_value(txn["transaction_amount"])
            posted = points_value(txn["rewards_earned"])
            expected = int((amount * rate * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        except (KeyError, ValueError, InvalidOperation) as exc:
            finding.update(status="unreviewable", reason="Missing or invalid field: " + str(exc))
            findings.append(finding)
            continue
        difference = expected - posted
        finding.update(
            account_id=account.get("account_id"), category=txn.get("category"),
            expected_rate_percent=str(rate * 100), expected_points=expected,
            posted_points=posted, difference_points=difference,
            difference_cash_back_dollars=str((Decimal(difference) / 100).quantize(Decimal("0.01"))),
            rate_basis=reason, promotion_applied=promo,
            named_exclusion_applied=merchant_is_excluded(txn.get("merchant_name")),
            status="match" if difference == 0 else "mismatch",
        )
        findings.append(finding)

    reviewable = [f for f in findings if f["status"] in {"match", "mismatch"}]
    mismatches = [f for f in findings if f["status"] == "mismatch"]
    return {
        "findings": findings,
        "summary": {
            "transaction_count": len(findings),
            "reviewable_count": len(reviewable),
            "match_count": sum(f["status"] == "match" for f in findings),
            "mismatch_count": len(mismatches),
            "unreviewable_count": sum(f["status"] == "unreviewable" for f in findings),
            "net_expected_minus_posted_points": sum(f.get("difference_points", 0) for f in reviewable),
            "net_expected_minus_posted_cash_back_dollars": str((Decimal(sum(f.get("difference_points", 0) for f in reviewable)) / 100).quantize(Decimal("0.01"))),
        },
    }


def main():
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(analyze(payload), indent=2, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
