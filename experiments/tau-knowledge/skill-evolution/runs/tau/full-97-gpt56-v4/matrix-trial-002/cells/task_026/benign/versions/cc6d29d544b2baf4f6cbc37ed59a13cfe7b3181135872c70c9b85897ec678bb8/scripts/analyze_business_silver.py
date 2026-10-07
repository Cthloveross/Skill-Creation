#!/usr/bin/env python3
"""Analyze completed Business Silver Rewards Card transactions.

Input (JSON stdin):
  {"accounts": [...], "transactions": [...]}
Accounts need account_id, card_type, date_of_account_open (YYYY-MM-DD).
Transactions need transaction_id, credit_card_type, merchant_name,
transaction_amount, transaction_date (YYYY-MM-DD), category, status, and
rewards_earned. Amount and rewards may be JSON numbers or strings.

Output is a JSON report. No external dependencies are used.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CARD = "Business Silver Rewards Card"
OFFER_START = date(2024, 11, 14)
OFFER_END = date(2025, 11, 14)
BONUS_RATE = Decimal("0.10")
STANDARD_RATE = Decimal("0.01")
POINTS_PER_DOLLAR = Decimal("100")

# These are category labels that directly correspond to the supplied eligible
# travel/software descriptions. Unlisted categories are evaluated at standard rate.
QUALIFYING_CATEGORIES = {
    "travel", "software", "airlines and air carriers", "airlines", "air carrier",
    "hotels", "hotel", "motels", "lodging", "car rental", "car rental agencies",
    "rideshare", "limousine", "taxi", "passenger rail", "intercity buses",
    "ferry", "parking", "parking facilities", "toll", "travel agencies",
    "online travel platforms",
}
EXCLUSION_BRANDS = (
    "concur", "sap concur", "expensify", "navan", "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online", "coursera",
    "udemy", "linkedin learning", "skillshare", "pluralsight",
)


def parse_date(value, field):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be YYYY-MM-DD")


def decimal_value(value, field):
    try:
        result = Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        raise ValueError(f"{field} must be numeric")
    if result < 0:
        raise ValueError(f"{field} cannot be negative")
    return result


def add_months(day, months):
    """Calendar addition retaining day where possible."""
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    # The opening days normally exist six months later; retain correctness for all dates.
    month_lengths = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                     31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(year, month, min(day.day, month_lengths[month - 1]))


def normalized(value):
    return " ".join(str(value or "").casefold().split())


def excluded_brand(merchant):
    """Return supplied excluded brand where merchant label clearly identifies it."""
    name = normalized(merchant)
    for brand in EXCLUSION_BRANDS:
        # Merchant descriptors such as "Microsoft 365" still identify Microsoft.
        if name == brand or name.startswith(brand + " ") or name.startswith(brand + ","):
            return brand
    return None


def is_qualifying_category(category):
    category = normalized(category)
    return category in QUALIFYING_CATEGORIES


def to_money(points):
    return (Decimal(points) / POINTS_PER_DOLLAR).quantize(Decimal("0.01"))


def main(payload):
    accounts = payload.get("accounts")
    transactions = payload.get("transactions")
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        return {"errors": ["accounts and transactions must both be arrays"], "reviewed_transactions": []}

    errors = []
    target_accounts = [a for a in accounts if isinstance(a, dict) and a.get("card_type") == CARD]
    if len(target_accounts) != 1:
        return {
            "errors": [f"expected exactly one {CARD} account; found {len(target_accounts)}"],
            "reviewed_transactions": [],
        }
    account = target_accounts[0]
    try:
        opened = parse_date(account.get("date_of_account_open"), "date_of_account_open")
    except ValueError as exc:
        return {"errors": [str(exc)], "reviewed_transactions": []}

    offer_eligible = OFFER_START <= opened <= OFFER_END
    promo_end = add_months(opened, 6)
    reviewed, skipped = [], []

    for txn in transactions:
        if not isinstance(txn, dict):
            skipped.append({"reason": "transaction is not an object"})
            continue
        ident = txn.get("transaction_id")
        if txn.get("credit_card_type") != CARD:
            skipped.append({"transaction_id": ident, "reason": "different card product"})
            continue
        if str(txn.get("status", "")).upper() != "COMPLETED":
            skipped.append({"transaction_id": ident, "reason": "transaction is not completed"})
            continue
        try:
            amount = decimal_value(txn.get("transaction_amount"), "transaction_amount")
            posted = decimal_value(txn.get("rewards_earned"), "rewards_earned")
            transacted = parse_date(txn.get("transaction_date"), "transaction_date")
        except ValueError as exc:
            skipped.append({"transaction_id": ident, "reason": str(exc)})
            continue

        category_qualifies = is_qualifying_category(txn.get("category"))
        exclusion = excluded_brand(txn.get("merchant_name"))
        base_rate = BONUS_RATE if category_qualifies and not exclusion else STANDARD_RATE
        promo_applies = offer_eligible and opened <= transacted < promo_end
        expected_rate = base_rate * (2 if promo_applies else 1)
        exact_points = amount * expected_rate * POINTS_PER_DOLLAR
        expected_points = exact_points.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        difference = expected_points - posted
        if difference > 0:
            finding = "possible_shortfall"
        elif difference < 0:
            finding = "posted_above_calculated_rate"
        else:
            finding = "matches_calculated_rate"

        reviewed.append({
            "transaction_id": ident,
            "transaction_date": transacted.isoformat(),
            "merchant_name": txn.get("merchant_name"),
            "stored_category": txn.get("category"),
            "amount_dollars": format(amount.quantize(Decimal("0.01")), ".2f"),
            "posted_points": format(posted, "f"),
            "posted_cash_back_dollars": format(to_money(posted), ".2f"),
            "category_is_known_qualifying": category_qualifies,
            "excluded_merchant_match": exclusion,
            "promo_applies": promo_applies,
            "base_rate_percent": format(base_rate * 100, "f"),
            "expected_rate_percent": format(expected_rate * 100, "f"),
            "expected_points": format(expected_points, "f"),
            "expected_cash_back_dollars": format(to_money(expected_points), ".2f"),
            "point_difference": format(difference, "f"),
            "cash_back_difference_dollars": format(to_money(difference), ".2f"),
            "finding": finding,
            "review_note": "Stored merchant category controls final eligibility; investigate disputed coding."
        })

    shortfalls = [r for r in reviewed if r["finding"] == "possible_shortfall"]
    total_shortfall = sum((Decimal(r["point_difference"]) for r in shortfalls), Decimal("0"))
    return {
        "card_type": CARD,
        "account_id": account.get("account_id"),
        "account_open_date": opened.isoformat(),
        "offer_eligible_by_open_date": offer_eligible,
        "promo_window_start": opened.isoformat() if offer_eligible else None,
        "promo_window_end_exclusive": promo_end.isoformat() if offer_eligible else None,
        "rounding_assumption": "Expected points are rounded to nearest whole point, half up.",
        "errors": errors,
        "reviewed_transactions": reviewed,
        "possible_shortfalls": shortfalls,
        "possible_shortfall_total_points": format(total_shortfall, "f"),
        "possible_shortfall_total_cash_back_dollars": format(to_money(total_shortfall), ".2f"),
        "skipped_transactions": skipped,
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"errors": [str(exc)], "reviewed_transactions": []}, sort_keys=True))
