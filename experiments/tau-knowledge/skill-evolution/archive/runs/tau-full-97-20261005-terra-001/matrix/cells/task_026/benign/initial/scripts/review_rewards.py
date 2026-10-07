#!/usr/bin/env python3
"""Calculate expected whole reward points for supported cash-back cards.

Input (stdin):
{
  "accounts": [{"card_type": str, "date_of_account_open": "YYYY-MM-DD"}, ...],
  "transactions": [{
    "transaction_id": str, "credit_card_type": str, "merchant_name": str,
    "transaction_amount": number|string, "transaction_date": "YYYY-MM-DD",
    "category": str, "status": str, "rewards_earned": number|string
  }, ...]
}

Output (stdout):
{
  "discrepancies": [review rows], "matches": [review rows],
  "skipped": [{"transaction_id": ..., "reason": ...}],
  "summary": {"reviewed": int, "discrepancy_count": int,
              "match_count": int, "skipped_count": int,
              "net_difference_points": int}
}

All rate decisions are based only on supplied posted categories and published
product rules. This program does not perform any banking action.
"""
import json
import re
import sys
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

BUSINESS = "business silver rewards card"
SILVER = "silver rewards card"
PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)
EXCLUDED = (
    "concur", "sap concur", "expensify", "navan", "apple", "microsoft",
    "dell", "xbox game pass", "playstation plus", "nintendo switch online",
    "coursera", "udemy", "linkedin learning", "skillshare", "pluralsight",
)


def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("must be YYYY-MM-DD")
    return datetime.strptime(value, "%Y-%m-%d").date()


def add_months(value, months):
    target = value.month - 1 + months
    year = value.year + target // 12
    month = target % 12 + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def parse_decimal(value, field):
    text = str(value).strip().replace(",", "")
    # Permit common transaction-history decorations such as "$12.34" or "42 points".
    text = re.sub(r"(?i)\bpoints?\b", "", text).replace("$", "").strip()
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError("%s is not numeric" % field)


def build_opening_dates(accounts):
    openings = {}
    malformed = set()
    for account in accounts:
        if not isinstance(account, dict):
            continue
        card = norm(account.get("card_type"))
        if card not in (BUSINESS, SILVER):
            continue
        try:
            opened = parse_date(account.get("date_of_account_open"))
        except ValueError:
            malformed.add(card)
            continue
        openings.setdefault(card, set()).add(opened)
    return openings, malformed


def contains_excluded_merchant(merchant):
    merchant_n = " " + norm(merchant) + " "
    for excluded in EXCLUDED:
        token = " " + excluded + " "
        if token in merchant_n:
            return excluded
    return None


def completed(status):
    # Only completed/posted purchases are safe to compare. A transaction source
    # may use POSTED as its equivalent completed status.
    return norm(status) in ("completed", "posted")


def calculate(txn, openings, malformed_cards):
    card = norm(txn.get("credit_card_type"))
    txn_id = txn.get("transaction_id")
    if not txn_id:
        raise ValueError("missing transaction_id")
    if card not in (BUSINESS, SILVER):
        raise ValueError("unsupported card type")
    if not completed(txn.get("status")):
        raise ValueError("transaction is not completed or posted")
    category = norm(txn.get("category"))
    if not category:
        raise ValueError("missing posted category")
    trans_date = parse_date(txn.get("transaction_date"))
    amount = parse_decimal(txn.get("transaction_amount"), "transaction_amount")
    if amount < 0:
        raise ValueError("negative transaction amount requires credit/refund handling")
    recorded = parse_decimal(txn.get("rewards_earned"), "rewards_earned")
    if recorded != recorded.to_integral_value():
        raise ValueError("recorded rewards are not whole points")

    eligible_category = category in ("travel", "software")
    rationale = []
    if card == SILVER:
        rate = Decimal("0.04") if eligible_category else Decimal("0.01")
        rationale.append("4% eligible category" if eligible_category else "1% standard category")
    else:
        if card in malformed_cards or card not in openings:
            raise ValueError("missing or invalid Business Silver account opening date")
        if len(openings[card]) != 1:
            raise ValueError("conflicting Business Silver account opening dates")
        excluded = contains_excluded_merchant(txn.get("merchant_name"))
        if eligible_category and not excluded:
            rate = Decimal("0.10")
            rationale.append("10% eligible category")
        else:
            rate = Decimal("0.01")
            if excluded:
                rationale.append("1% standard rate: excluded merchant " + excluded)
            else:
                rationale.append("1% standard category")
        opened = next(iter(openings[card]))
        if PROMO_START <= opened <= PROMO_END and opened <= trans_date < add_months(opened, 6):
            rate *= 2
            rationale.append("2x new-account promotion")
        elif not (PROMO_START <= opened <= PROMO_END):
            rationale.append("no promotion: account not opened during offer")
        else:
            rationale.append("no promotion: outside six-month account window")

    # Cash-back dollars = amount * rate; one point = one cent.
    expected = (amount * rate * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    expected_i = int(expected)
    recorded_i = int(recorded)
    return {
        "transaction_id": str(txn_id),
        "card_type": txn.get("credit_card_type"),
        "merchant_name": txn.get("merchant_name"),
        "transaction_date": txn.get("transaction_date"),
        "transaction_amount": format(amount.quantize(Decimal("0.01")), "f"),
        "category": txn.get("category"),
        "recorded_points": recorded_i,
        "expected_points": expected_i,
        "difference_points": expected_i - recorded_i,
        "applied_rate_percent": format(rate * 100, "f"),
        "rationale": "; ".join(rationale),
    }


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    accounts = payload.get("accounts")
    transactions = payload.get("transactions")
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        raise ValueError("accounts and transactions must be arrays")
    openings, malformed_cards = build_opening_dates(accounts)
    discrepancies, matches, skipped = [], [], []
    for txn in transactions:
        if not isinstance(txn, dict):
            skipped.append({"transaction_id": None, "reason": "transaction is not an object"})
            continue
        try:
            row = calculate(txn, openings, malformed_cards)
        except (ValueError, TypeError) as exc:
            skipped.append({"transaction_id": txn.get("transaction_id"), "reason": str(exc)})
            continue
        (discrepancies if row["difference_points"] else matches).append(row)
    return {
        "discrepancies": discrepancies,
        "matches": matches,
        "skipped": skipped,
        "summary": {
            "reviewed": len(discrepancies) + len(matches),
            "discrepancy_count": len(discrepancies),
            "match_count": len(matches),
            "skipped_count": len(skipped),
            "net_difference_points": sum(row["difference_points"] for row in discrepancies),
        },
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
