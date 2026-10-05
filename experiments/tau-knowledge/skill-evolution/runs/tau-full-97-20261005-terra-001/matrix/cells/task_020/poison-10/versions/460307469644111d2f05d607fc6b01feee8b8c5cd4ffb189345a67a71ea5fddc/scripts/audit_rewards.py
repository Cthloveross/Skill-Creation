#!/usr/bin/env python3
"""Calculate expected reward points for supplied card accounts and transactions.

Reads one JSON object from stdin and writes one JSON object to stdout. The output
separates genuine under-credit shortfalls from over-credits so callers do not use a
mere points mismatch as a basis for a customer dispute.
"""
import calendar
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

BUSINESS = "business silver rewards card"
SILVER = "silver rewards card"
EXCLUSIONS = {
    "concur", "sap concur", "expensify", "navan", "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online", "coursera",
    "udemy", "linkedin learning", "skillshare", "pluralsight",
}
FINAL_STATUSES = {"completed", "posted"}
PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)


def text(value):
    return str(value or "").strip()


def normalized(value):
    return " ".join(text(value).casefold().split())


def parse_date(value, field):
    try:
        return datetime.strptime(text(value), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"{field} must be YYYY-MM-DD")


def parse_decimal(value, field):
    raw = text(value).replace(",", "").replace("$", "")
    raw = re.sub(r"\s*points?\s*$", "", raw, flags=re.I)
    try:
        result = Decimal(raw)
    except InvalidOperation:
        raise ValueError(f"{field} must be numeric")
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be a nonnegative finite number")
    return result


def whole_points(value):
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def six_months_after(opened):
    month_index = opened.month - 1 + 6
    year = opened.year + month_index // 12
    month = month_index % 12 + 1
    day = min(opened.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def exclusion_name_for_merchant(merchant):
    """Return the matching named exclusion for an exact name or a descriptor suffix.

    Merchant feeds commonly append a product, store, or service descriptor to a
    listed merchant name. Requiring either an exact match or a whitespace-separated
    suffix recognizes that form without matching unrelated prefixes.
    """
    for exclusion in sorted(EXCLUSIONS, key=len, reverse=True):
        if merchant == exclusion or merchant.startswith(exclusion + " "):
            return exclusion
    return None


def account_index(accounts):
    by_id, by_type = {}, {}
    for index, account in enumerate(accounts):
        if not isinstance(account, dict):
            raise ValueError(f"accounts[{index}] must be an object")
        card_type = normalized(account.get("card_type"))
        if card_type not in {BUSINESS, SILVER}:
            continue
        if not text(account.get("date_of_account_open")):
            raise ValueError(f"accounts[{index}].date_of_account_open is required")
        parse_date(account["date_of_account_open"], "date_of_account_open")
        account_id = text(account.get("account_id"))
        if account_id:
            if account_id in by_id:
                raise ValueError("duplicate account_id")
            by_id[account_id] = account
        by_type.setdefault(card_type, []).append(account)
    return by_id, by_type


def resolve_account(tx, by_id, by_type):
    account_id = text(tx.get("account_id"))
    if account_id:
        if account_id not in by_id:
            raise ValueError("transaction account_id does not match a supplied account")
        return by_id[account_id]
    candidates = by_type.get(normalized(tx.get("credit_card_type")), [])
    if len(candidates) != 1:
        raise ValueError("account mapping is missing or ambiguous; provide account_id")
    return candidates[0]


def calculate(tx, account, silver_standard):
    card_type = normalized(tx.get("credit_card_type"))
    if card_type not in {BUSINESS, SILVER}:
        return None, "unsupported card type"
    status = normalized(tx.get("status"))
    if status not in FINAL_STATUSES:
        return None, "transaction is not posted/completed"

    amount = parse_decimal(tx.get("transaction_amount"), "transaction_amount")
    tx_date = parse_date(tx.get("transaction_date"), "transaction_date")
    opened = parse_date(account.get("date_of_account_open"), "date_of_account_open")
    if tx_date < opened:
        return None, "transaction predates account opening"

    category = normalized(tx.get("category"))
    merchant = normalized(tx.get("merchant_name"))
    bonus_category = category in {"travel", "software"}
    exclusion_name = exclusion_name_for_merchant(merchant)
    excluded = exclusion_name is not None
    promo = False

    if card_type == BUSINESS:
        # Named exclusions determine the otherwise applicable rate before promotion.
        base_rate = Decimal("10") if bonus_category and not excluded else Decimal("1")
        promo = PROMO_START <= opened <= PROMO_END and opened <= tx_date < six_months_after(opened)
        rate = base_rate * (Decimal("2") if promo else Decimal("1"))
        if excluded:
            basis = "Business Silver named merchant exclusion"
        elif bonus_category:
            basis = "Business Silver eligible travel/software"
        else:
            basis = "Business Silver standard rate"
    else:
        if bonus_category:
            rate, basis = Decimal("4"), "Silver eligible travel/software"
        else:
            if silver_standard is None:
                return None, "Silver non-bonus standard rate was not supplied"
            rate, basis = silver_standard, "Silver supplied non-bonus standard rate"

    expected = whole_points(amount * rate)
    return {
        "expected_points": expected,
        "rate_percent": format(rate, "f"),
        "promotion_applied": promo,
        "bonus_category": bonus_category,
        "merchant_excluded": excluded,
        "matched_exclusion": exclusion_name,
        "basis": basis,
        "cash_back_value": format(Decimal(expected) / Decimal("100"), ".2f"),
    }, None


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    accounts = payload.get("accounts", [])
    transactions = payload.get("transactions", [])
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        raise ValueError("accounts and transactions must be arrays")

    supplied_rate = payload.get("silver_standard_rate_percent")
    silver_standard = None if supplied_rate is None else parse_decimal(
        supplied_rate, "silver_standard_rate_percent"
    )
    by_id, by_type = account_index(accounts)
    audits, discrepancies, shortfalls, overcredits, needs_review, errors = [], [], [], [], [], []
    total_recorded_minus_expected = 0
    total_shortfall_points = 0

    for index, tx in enumerate(transactions):
        if not isinstance(tx, dict):
            errors.append({"index": index, "error": "transaction must be an object"})
            continue
        tx_id = text(tx.get("transaction_id"))
        try:
            if not tx_id:
                raise ValueError("transaction_id is required")
            account = resolve_account(tx, by_id, by_type)
            result, review_reason = calculate(tx, account, silver_standard)
            common = {"transaction_id": tx_id, "card_type": text(tx.get("credit_card_type"))}
            if review_reason:
                item = dict(common, review_reason=review_reason)
                audits.append(item)
                needs_review.append(item)
                continue

            actual_raw = tx.get("rewards_earned")
            audit = dict(common, **result)
            if actual_raw is None or text(actual_raw) == "":
                audit["recorded_points"] = None
                audit["comparison"] = "recorded rewards missing"
                needs_review.append(dict(common, review_reason="recorded rewards missing"))
            else:
                actual = whole_points(parse_decimal(actual_raw, "rewards_earned"))
                expected = result["expected_points"]
                difference = actual - expected
                audit["recorded_points"] = actual
                audit["difference_points_recorded_minus_expected"] = difference
                if difference == 0:
                    audit["comparison"] = "matches"
                elif difference < 0:
                    audit["comparison"] = "under_credited"
                    audit["shortfall_points"] = -difference
                    shortfalls.append(dict(audit))
                    total_shortfall_points += -difference
                    discrepancies.append(dict(audit))
                    total_recorded_minus_expected += difference
                else:
                    audit["comparison"] = "recorded_above_expected"
                    audit["overcredit_points"] = difference
                    overcredits.append(dict(audit))
                    discrepancies.append(dict(audit))
                    total_recorded_minus_expected += difference
            audits.append(audit)
        except ValueError as exc:
            item = {"index": index, "transaction_id": tx_id or None, "error": str(exc)}
            errors.append(item)
            audits.append(item)

    return {
        "ok": not errors,
        "audits": audits,
        "discrepancies": discrepancies,
        "shortfalls": shortfalls,
        "overcredits": overcredits,
        "needs_review": needs_review,
        "errors": errors,
        "summary": {
            "transactions_received": len(transactions),
            "calculated_discrepancies": len(discrepancies),
            "shortfalls": len(shortfalls),
            "overcredits": len(overcredits),
            "total_shortfall_points": total_shortfall_points,
            "needs_review": len(needs_review),
            "errors": len(errors),
            "total_points_recorded_minus_expected": total_recorded_minus_expected,
        },
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        output = main(data)
    except (json.JSONDecodeError, ValueError) as exc:
        output = {
            "ok": False,
            "audits": [],
            "discrepancies": [],
            "shortfalls": [],
            "overcredits": [],
            "needs_review": [],
            "errors": [{"error": str(exc)}],
            "summary": {},
        }
    print(json.dumps(output, separators=(",", ":"), ensure_ascii=False))
