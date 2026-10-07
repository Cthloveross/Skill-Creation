#!/usr/bin/env python3
"""Audit documented cash-back rules. Reads JSON stdin and writes JSON stdout."""
import calendar
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)
BUSINESS_CARD = "Business Silver Rewards Card"
SILVER_CARD = "Silver Rewards Card"
EXCLUSIONS = (
    "Concur", "SAP Concur", "Expensify", "Navan", "Apple", "Microsoft", "Dell",
    "Xbox Game Pass", "PlayStation Plus", "Nintendo Switch Online", "Coursera",
    "Udemy", "LinkedIn Learning", "Skillshare", "Pluralsight",
)


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a YYYY-MM-DD string")
    return datetime.strptime(value, "%Y-%m-%d").date()


def add_months(d, months):
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def money(value):
    try:
        result = Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        raise ValueError("transaction_amount is not a decimal amount")
    if result < 0:
        raise ValueError("transaction_amount cannot be negative")
    return result


def points(value):
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if not isinstance(value, str):
        raise ValueError("rewards_earned must be an integer or text such as '123 points'")
    match = re.fullmatch(r"\s*(\d+)\s*(?:points?)?\s*", value, flags=re.I)
    if not match:
        raise ValueError("rewards_earned does not contain a whole point value")
    return int(match.group(1))


def normalized(value):
    return re.sub(r"\s+", " ", str(value).strip().casefold())


def excluded_merchant(merchant):
    m = normalized(merchant)
    hits = [name for name in EXCLUSIONS if m == normalized(name) or m.startswith(normalized(name) + " ")]
    if not hits:
        return None
    # SAP Concur is more specific than Concur if both prefix rules match.
    return max(hits, key=len)


def policy_for(tx, opening_date, supplied):
    card = tx.get("credit_card_type")
    category = normalized(tx.get("category", ""))
    merchant = tx.get("merchant_name", "")
    tx_date = parse_date(tx.get("transaction_date"))

    if card == BUSINESS_CARD:
        qualifying = category in ("travel", "software")
        exclusion = excluded_merchant(merchant) if qualifying else None
        base = Decimal("10") if qualifying and not exclusion else Decimal("1")
        reason = "eligible recorded category" if qualifying and not exclusion else (
            "documented excluded merchant: " + exclusion if exclusion else "ordinary recorded category"
        )
        promo = PROMO_START <= opening_date <= PROMO_END and opening_date <= tx_date < add_months(opening_date, 6)
        return base * (2 if promo else 1), reason + ("; double-cash-back promotion" if promo else "")

    if card == SILVER_CARD:
        if category in ("travel", "software"):
            return Decimal("4"), "eligible recorded category"
        configured = supplied.get(card, {}) if isinstance(supplied, dict) else {}
        other = configured.get("other_rate_percent") if isinstance(configured, dict) else None
        if other is None:
            return None, "ordinary Silver Rewards Card rate is not documented in this skill"
        try:
            rate = Decimal(str(other))
        except InvalidOperation:
            return None, "configured other_rate_percent is invalid"
        if rate < 0:
            return None, "configured other_rate_percent cannot be negative"
        return rate, "documented supplemental ordinary rate"

    return None, "unsupported card type"


def audit(payload):
    accounts = payload.get("accounts")
    transactions = payload.get("transactions")
    supplied = payload.get("card_policies", {})
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        raise ValueError("accounts and transactions must be arrays")

    openings = {}
    errors = []
    for account in accounts:
        if not isinstance(account, dict):
            errors.append("ignored non-object account")
            continue
        card = account.get("card_type")
        try:
            opened = parse_date(account.get("date_of_account_open"))
        except ValueError as exc:
            errors.append("account %r: %s" % (card, exc))
            continue
        if card in openings:
            errors.append("duplicate account-opening date for card type %r" % card)
        else:
            openings[card] = opened

    seen_ids = set()
    results = []
    for tx in transactions:
        result = {"transaction_id": tx.get("transaction_id") if isinstance(tx, dict) else None}
        if not isinstance(tx, dict):
            result.update(disposition="review_needed", reason="transaction is not an object")
            results.append(result)
            continue
        txid = tx.get("transaction_id")
        if not isinstance(txid, str) or not txid:
            result.update(disposition="review_needed", reason="missing transaction_id")
            results.append(result)
            continue
        if txid in seen_ids:
            result.update(disposition="review_needed", reason="duplicate transaction_id")
            results.append(result)
            continue
        seen_ids.add(txid)
        if normalized(tx.get("status", "")) not in ("completed", "posted"):
            result.update(disposition="skipped", reason="transaction is not completed/posted")
            results.append(result)
            continue
        card = tx.get("credit_card_type")
        if card not in openings:
            result.update(disposition="review_needed", reason="no unique matching account-opening date")
            results.append(result)
            continue
        try:
            rate, reason = policy_for(tx, openings[card], supplied)
            if rate is None:
                result.update(disposition="review_needed", reason=reason)
                results.append(result)
                continue
            amount = money(tx.get("transaction_amount"))
            actual = points(tx.get("rewards_earned"))
            # amount * percentage gives point count: 1% of $1 = 1 point.
            expected = int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))
            result.update(
                disposition="match" if actual == expected else "mismatch",
                rate_percent=str(rate), expected_points=expected,
                actual_points=actual, reason=reason,
            )
        except (ValueError, TypeError) as exc:
            result.update(disposition="review_needed", reason=str(exc))
        results.append(result)
    return {"results": results, "errors": errors}


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(audit(payload), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"results": [], "errors": [str(exc)]}, separators=(",", ":")))


if __name__ == "__main__":
    main()
