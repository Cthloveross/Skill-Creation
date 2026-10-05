#!/usr/bin/env python3
"""Calculate auditable credit-card rewards. Reads JSON stdin and emits JSON stdout."""
import calendar
import json
import re
import sys
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)
BUSINESS_EXCLUSIONS = [
    "Concur", "SAP Concur", "Expensify", "Navan", "Apple", "Microsoft", "Dell",
    "Xbox Game Pass", "PlayStation Plus", "Nintendo Switch Online", "Coursera", "Udemy",
    "LinkedIn Learning", "Skillshare", "Pluralsight",
]
DEFAULT_POLICIES = {
    "Business Silver Rewards Card": {
        "base_rate": "0.01",
        "bonus_categories": {"travel": "0.10", "software": "0.10"},
        "excluded_merchants": BUSINESS_EXCLUSIONS,
    },
    "Silver Rewards Card": {
        "base_rate": None,
        "bonus_categories": {"travel": "0.04", "software": "0.04"},
        "excluded_merchants": [],
    },
}

def parse_date(value):
    return date.fromisoformat(str(value).strip())

def add_months(value, months):
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))

def decimal_value(value):
    text = str(value).replace(",", "")
    text = re.sub(r"[^0-9.\-]", "", text)
    if not text or text in {"-", "."}:
        raise InvalidOperation
    return Decimal(text)

def points_value(value):
    if isinstance(value, int):
        return value
    return int(decimal_value(value))

def normalized(value):
    return " ".join(re.findall(r"[a-z0-9]+", str(value).casefold()))

def merchant_is_excluded(merchant, exclusions):
    merchant_words = normalized(merchant).split()
    for exclusion in exclusions:
        excluded_words = normalized(exclusion).split()
        if merchant_words[:len(excluded_words)] == excluded_words:
            return True, exclusion
    return False, None

def merged_policy(card_type, supplied):
    base = DEFAULT_POLICIES.get(card_type)
    if base is None:
        return None
    result = {"base_rate": base["base_rate"], "bonus_categories": dict(base["bonus_categories"]),
              "excluded_merchants": list(base["excluded_merchants"])}
    update = supplied.get(card_type, {}) if isinstance(supplied, dict) else {}
    if "base_rate" in update:
        result["base_rate"] = update["base_rate"]
    if isinstance(update.get("bonus_categories"), dict):
        result["bonus_categories"].update({normalized(k): v for k, v in update["bonus_categories"].items()})
    if isinstance(update.get("excluded_merchants"), list):
        result["excluded_merchants"] = update["excluded_merchants"]
    return result

def audit(transaction, account_open, supplied):
    result = {"transaction_id": transaction.get("transaction_id"), "card_type": transaction.get("credit_card_type")}
    try:
        if str(transaction.get("status", "")).upper() != "COMPLETED":
            result.update(status="not_final", reason="Transaction is not a completed posted purchase")
            return result
        amount = decimal_value(transaction["transaction_amount"])
        if amount <= 0:
            result.update(status="not_final", reason="Transaction amount is zero, negative, returned, or refunded")
            return result
        txn_date = parse_date(transaction["transaction_date"])
        actual = points_value(transaction["rewards_earned"])
    except (KeyError, ValueError, InvalidOperation, TypeError):
        result.update(status="error", reason="Missing or invalid amount, date, status, or rewards value")
        return result
    policy = merged_policy(transaction.get("credit_card_type"), supplied)
    if policy is None:
        result.update(status="insufficient_policy", reason="No supported policy for this card type")
        return result
    category = normalized(transaction.get("category", ""))
    excluded, exclusion_name = merchant_is_excluded(transaction.get("merchant_name", ""), policy["excluded_merchants"])
    rules = []
    if excluded:
        rate_text = policy["base_rate"]
        rules.append("merchant_exclusion:" + exclusion_name)
    elif category in policy["bonus_categories"]:
        rate_text = policy["bonus_categories"][category]
        rules.append("bonus_category:" + category)
    else:
        rate_text = policy["base_rate"]
        rules.append("base_category")
    if rate_text is None:
        result.update(status="insufficient_policy", reason="Ordinary-category base rate is not documented", actual_points=actual, rules=rules)
        return result
    try:
        rate = Decimal(str(rate_text))
    except InvalidOperation:
        result.update(status="error", reason="Configured rate is invalid")
        return result
    if transaction.get("credit_card_type") == "Business Silver Rewards Card":
        if account_open is None:
            result.update(status="error", reason="Matching account opening date is missing")
            return result
        if PROMO_START <= account_open <= PROMO_END and account_open <= txn_date < add_months(account_open, 6):
            rate *= 2
            rules.append("double_cash_back_promotion")
    expected = int((amount * rate * Decimal(100)).to_integral_value(rounding=ROUND_FLOOR))
    difference = expected - actual
    status = "matches" if difference == 0 else ("underpaid" if difference > 0 else "overpaid_or_data_difference")
    result.update(status=status, amount=str(amount), rate=str(rate), expected_points=expected,
                  actual_points=actual, point_difference=difference, cash_difference=str(Decimal(max(difference, 0)) / 100), rules=rules)
    return result

def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({"errors": ["Input must be a JSON object"]}))
        return
    accounts = payload.get("accounts", [])
    openings = {}
    errors = []
    for account in accounts:
        try:
            openings[account["card_type"]] = parse_date(account["date_of_account_open"])
        except (KeyError, ValueError, TypeError):
            errors.append("An account has a missing or invalid card_type/date_of_account_open")
    results = []
    for transaction in payload.get("transactions", []):
        card_type = transaction.get("credit_card_type")
        if card_type not in openings:
            results.append({"transaction_id": transaction.get("transaction_id"), "card_type": card_type,
                            "status": "error", "reason": "No matching owned account with an opening date"})
        else:
            results.append(audit(transaction, openings[card_type], payload.get("policies", {})))
    counts = Counter(item["status"] for item in results)
    print(json.dumps({"results": results, "summary": {"counts": dict(counts), "dispute_candidates": [item["transaction_id"] for item in results if item["status"] == "underpaid"]}, "errors": errors}, indent=2))

if __name__ == "__main__":
    main()
