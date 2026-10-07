#!/usr/bin/env python3
"""Audit documented cash-back rules. Reads one JSON object from stdin, emits JSON."""
import calendar
import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

BUSINESS = "business silver rewards card"
SILVER = "silver rewards card"
QUALIFYING = {"travel", "software"}
EXCLUDED_MERCHANTS = (
    "concur", "sap concur", "expensify", "navan", "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online", "coursera",
    "udemy", "linkedin learning", "skillshare", "pluralsight",
)


def normalize(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def parse_date(value, field):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be an ISO YYYY-MM-DD date")


def parse_decimal(value, field):
    cleaned = str(value).replace("$", "").replace(",", "").strip()
    try:
        amount = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal amount")
    if amount < 0:
        raise ValueError(f"{field} cannot be negative")
    return amount


def parse_points(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("rewards_earned is required and must be a whole number")
    match = re.search(r"-?\d+(?:\.0+)?", str(value).replace(",", ""))
    if not match:
        raise ValueError("rewards_earned must contain a whole number of points")
    number = Decimal(match.group(0))
    if number != number.to_integral_value():
        raise ValueError("rewards_earned must be a whole number of points")
    return int(number)


def add_calendar_months(start, months):
    target = start.month - 1 + months
    year = start.year + target // 12
    month = target % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def merchant_is_excluded(merchant):
    name = normalize(merchant)
    # Exact matching or a named product/service variation prevents substring matches
    # such as an unrelated merchant merely containing a brand fragment.
    for excluded in EXCLUDED_MERCHANTS:
        if name == excluded or name.startswith(excluded + " "):
            return excluded
    return None


def account_open_dates(accounts):
    result = {}
    for index, account in enumerate(accounts):
        card = normalize(account.get("card_type"))
        if card != BUSINESS:
            continue
        try:
            result[card] = parse_date(account.get("date_of_account_open"),
                                      f"accounts[{index}].date_of_account_open")
        except ValueError:
            # Absence is surfaced when a Business transaction is evaluated.
            result[card] = None
    return result


def rate_for(txn, business_open, promo):
    card = normalize(txn.get("credit_card_type"))
    category = normalize(txn.get("category"))
    activity_date = parse_date(txn.get("posted_date") or txn.get("transaction_date"),
                               "posted_date or transaction_date")
    excluded = merchant_is_excluded(txn.get("merchant_name")) if card == BUSINESS else None

    if card == BUSINESS:
        is_bonus_category = category in QUALIFYING and excluded is None
        base_rate = Decimal("0.10") if is_bonus_category else Decimal("0.01")
        if business_open is None:
            raise ValueError("Business Silver account opening date is required to assess promotion eligibility")
        offer_eligible = promo["start"] <= business_open <= promo["end"]
        promo_end = add_calendar_months(business_open, promo["months"])
        promotion_applied = offer_eligible and business_open <= activity_date < promo_end
        rate = base_rate * (Decimal(2) if promotion_applied else Decimal(1))
        basis = "Business Silver " + ("eligible travel/software" if is_bonus_category else "standard")
        if excluded:
            basis += f"; excluded merchant family: {excluded}"
        if promotion_applied:
            basis += "; new-customer double-cash-back promotion applied"
        return rate, basis, promotion_applied, excluded

    if card == SILVER:
        rate = Decimal("0.04") if category in QUALIFYING else Decimal("0.01")
        basis = "Silver eligible travel/software" if category in QUALIFYING else "Silver standard purchase"
        return rate, basis, False, None

    raise ValueError("unsupported card type")


def money(points):
    return format((Decimal(points) / Decimal(100)).quantize(Decimal("0.01")), "f")


def audit(payload):
    accounts = payload.get("accounts", [])
    transactions = payload.get("transactions", [])
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        raise ValueError("accounts and transactions must both be arrays")

    override = payload.get("business_promo") or {}
    promo = {
        "start": parse_date(override.get("promo_start", "2024-11-14"), "business_promo.promo_start"),
        "end": parse_date(override.get("promo_end", "2025-11-14"), "business_promo.promo_end"),
        "months": int(override.get("months", 6)),
    }
    if promo["months"] <= 0 or promo["start"] > promo["end"]:
        raise ValueError("business_promo dates/months are invalid")
    # Kept configurable without changing code if a documented Silver ordinary rate changes.
    silver_rate = parse_decimal(payload.get("silver_standard_rate", "0.01"), "silver_standard_rate")
    if silver_rate < 0 or silver_rate > 1:
        raise ValueError("silver_standard_rate must be between 0 and 1")

    # Temporarily substitute configured Silver rate in a local calculation path.
    opens = account_open_dates(accounts)
    audits, discrepancies, not_audited, input_errors = [], [], [], []
    for index, txn in enumerate(transactions):
        if not isinstance(txn, dict):
            input_errors.append({"index": index, "error": "transaction must be an object"})
            continue
        identifier = txn.get("transaction_id")
        status = normalize(txn.get("status"))
        if status not in {"completed", "posted"}:
            not_audited.append({"transaction_id": identifier, "reason": "transaction is not completed/posted"})
            continue
        try:
            card = normalize(txn.get("credit_card_type"))
            if card not in {BUSINESS, SILVER}:
                raise ValueError("unsupported card type")
            amount = parse_decimal(txn.get("transaction_amount"), "transaction_amount")
            actual = parse_points(txn.get("rewards_earned"))
            rate, basis, promoted, excluded = rate_for(txn, opens.get(BUSINESS), promo)
            if card == SILVER and normalize(txn.get("category")) not in QUALIFYING:
                rate = silver_rate
            expected = int((amount * rate * Decimal(100)).to_integral_value(rounding=ROUND_FLOOR))
            record = {
                "transaction_id": identifier,
                "card_type": txn.get("credit_card_type"),
                "merchant_name": txn.get("merchant_name"),
                "category": txn.get("category"),
                "activity_date": str(txn.get("posted_date") or txn.get("transaction_date")),
                "amount": format(amount, "f"),
                "rate": format(rate * 100, "f") + "%",
                "basis": basis,
                "promotion_applied": promoted,
                "excluded_merchant_family": excluded,
                "actual_points": actual,
                "actual_cash_back": money(actual),
                "expected_points": expected,
                "expected_cash_back": money(expected),
                "point_difference": actual - expected,
                "cash_back_difference": money(actual - expected),
                "matches_policy": actual == expected,
            }
            audits.append(record)
            if not record["matches_policy"]:
                discrepancies.append(record)
        except (ValueError, TypeError, KeyError) as exc:
            input_errors.append({"index": index, "transaction_id": identifier, "error": str(exc)})

    return {
        "audits": audits,
        "discrepancies": discrepancies,
        "not_audited": not_audited,
        "input_errors": input_errors,
        "summary": {
            "audited_transactions": len(audits),
            "matching_transactions": sum(1 for item in audits if item["matches_policy"]),
            "discrepancy_count": len(discrepancies),
            "not_audited_count": len(not_audited),
            "input_error_count": len(input_errors),
            "calculation": "expected points = floor(amount × applicable cash-back rate × 100)"
        }
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(audit(payload), indent=2, sort_keys=True))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        print(json.dumps({"audits": [], "discrepancies": [], "not_audited": [],
                          "input_errors": [{"error": str(exc)}],
                          "summary": {"audited_transactions": 0, "matching_transactions": 0,
                                      "discrepancy_count": 0, "not_audited_count": 0,
                                      "input_error_count": 1}}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
