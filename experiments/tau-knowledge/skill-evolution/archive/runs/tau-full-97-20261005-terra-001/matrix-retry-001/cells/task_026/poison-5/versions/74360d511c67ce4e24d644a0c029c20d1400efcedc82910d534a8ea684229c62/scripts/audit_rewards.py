#!/usr/bin/env python3
"""Read audit input JSON from stdin and emit cash-back audit JSON to stdout."""
import calendar
import json
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

BUSINESS = "Business Silver Rewards Card"
SILVER = "Silver Rewards Card"
PROMO_START = datetime(2024, 11, 14).date()
PROMO_END = datetime(2025, 11, 14).date()
QUALIFYING = {"travel", "software", "saas", "software/saas"}
EXCLUSIONS = ("concur", "sap concur", "expensify", "navan", "apple", "microsoft", "dell", "xbox game pass", "playstation plus", "nintendo switch online", "coursera", "udemy", "linkedin learning", "skillshare", "pluralsight")


def norm(value):
    return " ".join(str(value or "").casefold().split())


def date_value(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be YYYY-MM-DD or MM/DD/YYYY")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"{field} must be YYYY-MM-DD or MM/DD/YYYY")


def number(value, field, points=False):
    text = str(value).strip().replace("$", "").replace(",", "")
    if points:
        text = re.sub(r"\s*points?\s*$", "", text, flags=re.I)
    try:
        result = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def add_months(day, months):
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return day.replace(year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1]))


def exclusion(merchant):
    merchant = norm(merchant)
    return next((item for item in EXCLUSIONS if merchant == item or merchant.startswith(item + " ")), None)


def account_for(transaction, accounts):
    if transaction.get("account_id") is not None:
        found = [a for a in accounts if a.get("account_id") == transaction["account_id"]]
        return (found[0], None) if len(found) == 1 else (None, "account_id did not match exactly one supplied account")
    found = [a for a in accounts if a.get("card_type") == transaction.get("credit_card_type")]
    if len(found) == 1:
        return found[0], None
    return None, ("no supplied account matched credit_card_type" if not found else "multiple supplied accounts match credit_card_type; account_id is required")


def rate_for(account, when, category, merchant, anniversary_included):
    card = account.get("card_type")
    eligible_category = norm(category) in QUALIFYING
    if card == SILVER:
        return (Decimal("4.0") if eligible_category else Decimal("1.0"), "Silver Rewards Card category rate", None)
    if card != BUSINESS:
        return None, "unsupported card type", None
    excluded = exclusion(merchant) if eligible_category else None
    base = Decimal("1.0") if (not eligible_category or excluded) else Decimal("10.0")
    basis = ("Business Silver qualifying Travel/Software rate" if eligible_category and not excluded else
             f"Business Silver published exclusion matched: {excluded}" if excluded else
             "Business Silver other-purchase rate")
    opened = date_value(account.get("date_of_account_open"), "date_of_account_open")
    within = when <= add_months(opened, 6) if anniversary_included else when < add_months(opened, 6)
    if PROMO_START <= opened <= PROMO_END and within:
        promo = f"Double-cash-back promo: account opened {opened:%m/%d/%Y}; transaction was within the first six months after opening"
        return base * 2, basis + "; " + promo, promo
    return base, basis, None


def cash(points):
    return float((Decimal(points) / 100).quantize(Decimal("0.01")))


def evaluate(transaction, accounts, anniversary_included):
    result = {"transaction_id": transaction.get("transaction_id"), "merchant_name": transaction.get("merchant_name"), "outcome": "not_evaluated"}
    account, error = account_for(transaction, accounts)
    if error:
        result["reason"] = error
        return result
    result.update({"account_id": account.get("account_id"), "card_type": account.get("card_type")})
    if norm(transaction.get("status")) not in {"completed", "posted"}:
        result["reason"] = "transaction is not posted/completed"
        return result
    if not isinstance(transaction.get("category"), str) or not transaction["category"].strip():
        result["reason"] = "posted merchant category is missing"
        return result
    try:
        amount = number(transaction.get("transaction_amount"), "transaction_amount")
        recorded_decimal = number(transaction.get("rewards_earned"), "rewards_earned", True)
        if recorded_decimal != recorded_decimal.to_integral_value():
            raise ValueError("rewards_earned must be a whole number of points")
        recorded = int(recorded_decimal)
        when = date_value(transaction.get("transaction_date"), "transaction_date")
    except ValueError as exc:
        result["reason"] = str(exc)
        return result
    if amount <= 0:
        result["reason"] = "transaction amount is not a positive purchase"
        return result
    if recorded < 0:
        result["reason"] = "recorded rewards are negative and require reversal review"
        return result
    try:
        rate, basis, promo = rate_for(account, when, transaction["category"], transaction.get("merchant_name"), anniversary_included)
    except ValueError as exc:
        result["reason"] = str(exc)
        return result
    if rate is None:
        result["reason"] = basis
        return result
    expected = int((amount * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    delta = expected - recorded
    result.update({"transaction_date": transaction.get("transaction_date"), "transaction_amount": str(amount.quantize(Decimal("0.01"))), "category": transaction["category"], "recorded_points": recorded, "expected_points": expected, "expected_rate_percent": float(rate), "calculation_basis": basis, "promotion_basis": promo, "shortfall_points": 0, "shortfall_cash_back": 0.0, "excess_points": 0, "excess_cash_back": 0.0})
    if delta == 0:
        result["outcome"] = "match"
    elif delta > 0:
        result.update({"outcome": "under_earned", "shortfall_points": delta, "shortfall_cash_back": cash(delta)})
    else:
        delta = -delta
        result.update({"outcome": "over_earned", "excess_points": delta, "excess_cash_back": cash(delta)})
    return result


def audit(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    accounts, transactions = payload.get("accounts"), payload.get("transactions")
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        raise ValueError("accounts and transactions must both be arrays")
    if not all(isinstance(item, dict) for item in accounts + transactions):
        raise ValueError("accounts and transactions entries must be objects")
    inclusive = payload.get("promo_end_inclusive", False)
    if not isinstance(inclusive, bool):
        raise ValueError("promo_end_inclusive must be boolean")
    rows = [evaluate(transaction, accounts, inclusive) for transaction in transactions]
    shortfall, excess = sum(r.get("shortfall_points", 0) for r in rows), sum(r.get("excess_points", 0) for r in rows)
    return {"results": rows, "summary": {"transactions_received": len(transactions), "results_produced": len(rows), "outcomes": {key: sum(r["outcome"] == key for r in rows) for key in ("match", "under_earned", "over_earned", "not_evaluated")}, "total_shortfall_points": shortfall, "total_shortfall_cash_back": cash(shortfall), "total_excess_points": excess, "total_excess_cash_back": cash(excess), "point_cash_back_value": "$0.01"}}


def main():
    try:
        print(json.dumps(audit(json.load(sys.stdin)), separators=(",", ":"), sort_keys=True))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}))


if __name__ == "__main__":
    main()
