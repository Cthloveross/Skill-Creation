#!/usr/bin/env python3
"""Deterministic cash-back audit calculator. Reads one JSON object from stdin, emits one JSON object."""
import calendar
import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

BUSINESS = "Business Silver Rewards Card"
PERSONAL = "Silver Rewards Card"
QUALIFYING = {"travel", "software"}
EXCLUSION_TOKENS = (
    "sap concur", "concur", "expensify", "navan", "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online", "coursera", "udemy",
    "linkedin learning", "skillshare", "pluralsight",
)
NON_PURCHASE_WORDS = ("gift card", "person-to-person", "person to person", "fee", "interest", "insurance")


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be YYYY-MM-DD")
    return date.fromisoformat(value)


def add_months(value, months):
    target = value.month - 1 + months
    year = value.year + target // 12
    month = target % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def amount_to_decimal(value):
    text = str(value).strip().replace("$", "").replace(",", "")
    amount = Decimal(text)
    if amount < 0:
        raise ValueError("transaction_amount must not be negative")
    return amount


def points_value(value):
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if not match:
        raise ValueError("rewards_earned must contain a numeric point value")
    points = Decimal(match.group(0))
    if points != points.to_integral_value():
        raise ValueError("rewards_earned must be a whole point value")
    return int(points)


def normalize(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def is_excluded_merchant(merchant):
    name = normalize(merchant)
    # These are documented merchant families. The output retains a review flag because
    # a display name does not establish merchant-of-record or processor coding.
    return any(token in name for token in EXCLUSION_TOKENS)


def promo_status(opened, txn_date, promo):
    start = parse_date(promo["offer_start"])
    end = parse_date(promo["offer_end"])
    if not (start <= opened <= end):
        return False, False
    anniversary = add_months(opened, 6)
    if txn_date == anniversary and "end_inclusive" not in promo:
        return False, True
    inclusive = bool(promo.get("end_inclusive", False))
    active = opened <= txn_date <= anniversary if inclusive else opened <= txn_date < anniversary
    return active, False


def account_for(transaction, accounts):
    tx_account = transaction.get("account_id")
    if tx_account:
        matches = [a for a in accounts if a.get("account_id") == tx_account]
    else:
        matches = [a for a in accounts if a.get("card_type") == transaction.get("credit_card_type")]
    if len(matches) != 1:
        return None
    return matches[0]


def manual(transaction_id, actual, flags):
    return {
        "transaction_id": transaction_id,
        "expected_points": None,
        "actual_points": actual,
        "finding": "manual_review",
        "applied_rate_percent": None,
        "flags": flags,
    }


def audit(transaction, accounts, promo):
    txid = transaction.get("transaction_id")
    if not txid:
        return manual(None, None, ["missing_transaction_id"])
    try:
        actual = points_value(transaction.get("rewards_earned"))
    except (ValueError, InvalidOperation):
        actual = None
    status = normalize(transaction.get("status", ""))
    if status not in {"completed", "posted"}:
        return manual(txid, actual, ["transaction_not_posted_or_completed"])
    category = normalize(transaction.get("category", ""))
    merchant = transaction.get("merchant_name", "")
    descriptor = normalize(" ".join([str(merchant), str(transaction.get("description", ""))]))
    if not category:
        return manual(txid, actual, ["missing_posted_category"])
    if any(word in descriptor for word in NON_PURCHASE_WORDS):
        return manual(txid, actual, ["potential_ineligible_or_nonpurchase_transaction"])
    if bool(transaction.get("is_returned")) or bool(transaction.get("is_refunded")) or "refund" in status or "return" in status:
        return manual(txid, actual, ["returned_or_refunded_rewards_must_be_reviewed"])
    account = account_for(transaction, accounts)
    if not account:
        return manual(txid, actual, ["missing_or_ambiguous_account_mapping"])
    card = transaction.get("credit_card_type")
    if card not in {BUSINESS, PERSONAL}:
        return manual(txid, actual, ["unsupported_card_type"])
    try:
        txn_date = parse_date(transaction.get("transaction_date"))
        amount = amount_to_decimal(transaction.get("transaction_amount"))
        opened = parse_date(account.get("date_of_account_open"))
    except (ValueError, InvalidOperation, TypeError) as exc:
        return manual(txid, actual, ["invalid_amount_or_date: " + str(exc)])

    flags = []
    rate = Decimal("1")
    if card == PERSONAL:
        if category in QUALIFYING:
            rate = Decimal("4")
            flags.append("personal_travel_or_software_rate")
        else:
            flags.append("personal_standard_rate")
    else:
        excluded = is_excluded_merchant(merchant)
        if excluded:
            flags.extend(["documented_business_exclusion_candidate", "verify_merchant_of_record_for_exclusion"])
        elif category in QUALIFYING:
            rate = Decimal("10")
            flags.append("business_travel_or_software_rate")
        else:
            flags.append("business_standard_rate")
        active, boundary_uncertain = promo_status(opened, txn_date, promo)
        if boundary_uncertain:
            return manual(txid, actual, flags + ["six_month_promotion_boundary_requires_policy_confirmation"])
        if active:
            rate *= Decimal("2")
            flags.append("eligible_business_double_cash_back_promotion")

    expected = int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))
    finding = "match" if actual == expected else ("undercredited" if actual is not None and actual < expected else "overcredited")
    if actual is None:
        return manual(txid, None, flags + ["invalid_actual_rewards_value"])
    return {
        "transaction_id": txid,
        "expected_points": expected,
        "actual_points": actual,
        "difference_points": expected - actual,
        "finding": finding,
        "applied_rate_percent": str(rate),
        "flags": flags,
    }


def main():
    try:
        payload = json.load(sys.stdin)
        accounts = payload.get("accounts")
        transactions = payload.get("transactions")
        if not isinstance(accounts, list) or not isinstance(transactions, list):
            raise ValueError("accounts and transactions must be arrays")
        promo = {"offer_start": "2024-11-14", "offer_end": "2025-11-14"}
        supplied_promo = payload.get("promotion")
        if supplied_promo is not None:
            if not isinstance(supplied_promo, dict):
                raise ValueError("promotion must be an object")
            promo.update(supplied_promo)
        results = [audit(tx, accounts, promo) if isinstance(tx, dict) else manual(None, None, ["transaction_is_not_an_object"]) for tx in transactions]
        summary = {"total": len(results), "match": 0, "undercredited": 0, "overcredited": 0, "manual_review": 0}
        for result in results:
            summary[result["finding"]] += 1
        print(json.dumps({"results": results, "summary": summary}, separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
