#!/usr/bin/env python3
"""Analyze posted rewards for Silver and Business Silver cash-back cards.
Read one JSON object from stdin and write one JSON result object to stdout.
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
# Normalized merchant names, not substrings: e.g., an unrelated "Applebee's"
# must not be classified as the named Apple exclusion.
EXCLUSIONS = {
    "concur", "sap concur", "expensify", "navan", "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online", "coursera",
    "udemy", "linkedin learning", "skillshare", "pluralsight",
}
DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y")
# These labels are only used when the posted category itself is unequivocal.
# Do not infer a gift-card or P2P purchase from an ordinary merchant name.
SILVER_ZERO_REWARD_CATEGORIES = {
    "gift card", "gift cards", "person to person", "person-to-person", "p2p",
    "fee", "fees", "interest", "bank interest", "bank fee",
    "insurance premium", "insurance premiums",
}


def parse_date(value):
    text = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError("date must use YYYY-MM-DD or MM/DD/YYYY")


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
    """Match a listed merchant or its ordinary product/service suffix only."""
    name = norm(merchant)
    if name in EXCLUSIONS:
        return True
    # Tool data commonly names a service as e.g. "Microsoft 365".  Require the
    # listed merchant at the start and a separating space, avoiding word fragments.
    return any(name.startswith(item + " ") for item in EXCLUSIONS)


def eligible_category(category):
    return norm(category) in {"travel", "software", "saas"}


def silver_zero_reward_category(category):
    return norm(category) in SILVER_ZERO_REWARD_CATEGORIES


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
        if silver_zero_reward_category(transaction.get("category")):
            return Decimal("0"), "Silver nonqualifying transaction category", False
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
    # The published offer end determines eligible opening dates.  Once an
    # account qualifies, its six-month window is measured from its own opening
    # date and is not capped by the sign-up offer end.
    promo_last_day = add_months(opened, 6)
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
        if not isinstance(txn, dict):
            findings.append({"status": "unreviewable", "reason": "Transaction must be an object."})
            continue
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
        if not norm(txn.get("category")):
            finding.update(status="unreviewable", reason="Missing posted merchant category; do not infer bonus eligibility.")
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
            expected_cash_back_dollars=str((Decimal(expected) / 100).quantize(Decimal("0.01"))),
            posted_points=posted,
            posted_cash_back_dollars=str((Decimal(posted) / 100).quantize(Decimal("0.01"))),
            difference_points=difference,
            difference_cash_back_dollars=str((Decimal(difference) / 100).quantize(Decimal("0.01"))),
            rate_basis=reason, promotion_applied=promo,
            named_exclusion_applied=merchant_is_excluded(txn.get("merchant_name")),
            status="match" if difference == 0 else "mismatch",
        )
        findings.append(finding)

    reviewable = [f for f in findings if f["status"] in {"match", "mismatch"}]
    return {
        "findings": findings,
        "summary": {
            "transaction_count": len(findings),
            "reviewable_count": len(reviewable),
            "match_count": sum(f["status"] == "match" for f in findings),
            "mismatch_count": sum(f["status"] == "mismatch" for f in findings),
            "unreviewable_count": sum(f["status"] == "unreviewable" for f in findings),
            "net_expected_minus_posted_points": sum(f.get("difference_points", 0) for f in reviewable),
            "net_expected_minus_posted_cash_back_dollars": str((Decimal(sum(f.get("difference_points", 0) for f in reviewable)) / 100).quantize(Decimal("0.01"))),
        },
    }


def main():
    try:
        print(json.dumps(analyze(json.load(sys.stdin)), indent=2, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
