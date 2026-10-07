#!/usr/bin/env python3
"""Policy calculation helper for Business Silver Rewards Card transaction reviews.

Read JSON from stdin and emit JSON to stdout.  See SKILL.md for schema.
"""
import calendar
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

DEFAULT_EXCLUSIONS = [
    "Concur", "SAP Concur", "Expensify", "Navan",
    "Apple", "Microsoft", "Dell",
    "Xbox Game Pass", "PlayStation Plus", "Nintendo Switch Online",
    "Coursera", "Udemy", "LinkedIn Learning", "Skillshare", "Pluralsight",
]
BONUS_CATEGORIES = {"travel", "software"}


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD)") from exc


def add_months(value, months):
    month_number = value.month - 1 + months
    year = value.year + month_number // 12
    month = month_number % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def money(value, field):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal number") from exc
    if amount < 0:
        raise ValueError(f"{field} must not be negative")
    return amount


def points(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if str(value).strip() not in {str(number), f"{number}.0"} and not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    if number < 0:
        raise ValueError(f"{field} must not be negative")
    return number


def normalized(text):
    return " ".join(str(text).casefold().split())


def is_excluded(merchant, exclusions):
    name = normalized(merchant)
    for exclusion in exclusions:
        candidate = normalized(exclusion)
        # Match a documented merchant name, including a normal suffix such as
        # "Microsoft 365", but not an unrelated word with the same prefix.
        if name == candidate or name.startswith(candidate + " "):
            return True
    return False


def promotion_status(opened, transaction_day, promo):
    if not promo or promo.get("enabled", True) is False:
        return False, "not_enabled"
    start = parse_date(promo.get("start_date"), "promo.start_date")
    end = parse_date(promo.get("end_date"), "promo.end_date")
    months = promo.get("months", 6)
    if not isinstance(months, int) or isinstance(months, bool) or months <= 0:
        raise ValueError("promo.months must be a positive integer")
    if end < start:
        raise ValueError("promo.end_date must not precede promo.start_date")
    if not (start <= opened <= end):
        return False, "account_not_opened_during_offer"
    if transaction_day < opened:
        return False, "before_account_opening"
    # Date-only data has no time-of-day. Treat the six-month anniversary as
    # included and expose that assumption in output.
    if transaction_day <= add_months(opened, months):
        return True, "within_promotional_window"
    return False, "after_promotional_window"


def assess_transaction(txn, opened, review_day, promo, exclusions):
    required = ["transaction_id", "merchant_name", "transaction_amount", "transaction_date", "category", "status"]
    missing = [key for key in required if key not in txn]
    if missing:
        raise ValueError("transaction missing field(s): " + ", ".join(missing))
    reward_key = "rewards_earned" if "rewards_earned" in txn else "reward_points" if "reward_points" in txn else None
    if reward_key is None:
        raise ValueError("transaction missing rewards_earned or reward_points")
    transaction_day = parse_date(txn["transaction_date"], "transaction.transaction_date")
    if transaction_day > review_day:
        raise ValueError("transaction date is after review_date")
    amount = money(txn["transaction_amount"], "transaction.transaction_amount")
    earned = points(txn[reward_key], "transaction." + reward_key)
    merchant = str(txn["merchant_name"])
    category = normalized(txn["category"])
    status = str(txn["status"]).upper()
    promoted, promo_reason = promotion_status(opened, transaction_day, promo)
    multiplier = Decimal("2") if promoted else Decimal("1")
    exclusion = is_excluded(merchant, exclusions)
    coding_confirmed = txn.get("merchant_category_confirmed") is True

    output = {
        "transaction_id": str(txn["transaction_id"]),
        "merchant_name": merchant,
        "transaction_date": transaction_day.isoformat(),
        "recorded_points": earned,
        "recorded_cash_back_dollars": format(Decimal(earned) / Decimal(100), ".2f"),
        "status": status,
        "promotion_applied_by_policy": promoted,
        "promotion_reason": promo_reason,
        "merchant_is_documented_exclusion": exclusion,
    }
    if status != "COMPLETED":
        output.update({"assessment": "not_reviewed", "reason": "transaction_not_completed"})
        return output

    if exclusion or category not in BONUS_CATEGORIES:
        base_rate = Decimal("0.01")
        basis = "documented_exclusion" if exclusion else "non_bonus_category"
        determinate = True
    elif coding_confirmed:
        base_rate = Decimal("0.10")
        basis = "confirmed_qualifying_travel_or_software_coding"
        determinate = True
    else:
        # Calculate the conditional bonus expectation, but do not claim it is
        # owed without confirmation of how the merchant processed the charge.
        base_rate = Decimal("0.10")
        basis = "travel_or_software_category_needs_coding_confirmation"
        determinate = False

    rate = base_rate * multiplier
    expected = int((amount * rate * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    output.update({
        "calculation_basis": basis,
        "policy_rate_percent": format(rate * 100, "f"),
        "expected_points": expected,
        "expected_cash_back_dollars": format(Decimal(expected) / Decimal(100), ".2f"),
        "point_difference_expected_minus_recorded": expected - earned,
    })
    if expected == earned:
        output["assessment"] = "consistent" if determinate else "conditionally_consistent"
    elif determinate:
        output["assessment"] = "confirmed_mismatch"
    else:
        output["assessment"] = "conditional_mismatch"
    return output


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    opened = parse_date(payload.get("account_open_date"), "account_open_date")
    review_day = parse_date(payload.get("review_date"), "review_date")
    if review_day < opened:
        raise ValueError("review_date must not precede account_open_date")
    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        raise ValueError("transactions must be a list")
    exclusions = payload.get("excluded_merchants", DEFAULT_EXCLUSIONS)
    if not isinstance(exclusions, list) or not all(isinstance(x, str) for x in exclusions):
        raise ValueError("excluded_merchants must be a list of merchant-name strings")
    promo = payload.get("promo")
    if promo is not None and not isinstance(promo, dict):
        raise ValueError("promo must be an object when provided")
    assessments = [assess_transaction(t, opened, review_day, promo, exclusions) for t in transactions]
    candidates = [x for x in assessments if x["assessment"] in {"confirmed_mismatch", "conditional_mismatch"}]
    return {
        "account_open_date": opened.isoformat(),
        "review_date": review_day.isoformat(),
        "six_month_anniversary_inclusive_assumption": add_months(opened, (promo or {}).get("months", 6)).isoformat() if (promo or {}).get("enabled", True) else None,
        "assessments": assessments,
        "review_candidates": candidates,
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), separators=(",", ":"), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
