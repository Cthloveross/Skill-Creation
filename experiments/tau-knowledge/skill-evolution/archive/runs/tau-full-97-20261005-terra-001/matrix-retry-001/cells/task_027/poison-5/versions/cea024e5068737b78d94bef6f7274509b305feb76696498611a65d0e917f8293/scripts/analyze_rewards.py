#!/usr/bin/env python3
"""Analyze documented Silver and Business Silver cash-back rewards.

Reads a JSON object from stdin with a `transactions` list and writes a JSON
object containing an analysis for every supplied transaction to stdout.
"""
import calendar
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

BUSINESS_CARD = "Business Silver Rewards Card"
SILVER_CARD = "Silver Rewards Card"
PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)

# Lowercase documented merchant names. Prefix matching accepts a documented
# merchant followed by a plan/product suffix, while avoiding substring matches.
BUSINESS_EXCLUSIONS = (
    "concur", "sap concur", "expensify", "navan",
    "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online",
    "coursera", "udemy", "linkedin learning", "skillshare", "pluralsight",
)


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be YYYY-MM-DD")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def add_calendar_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def normalized(value):
    return re.sub(r"\s+", " ", str(value).strip().casefold())


def is_excluded_merchant(merchant):
    name = normalized(merchant)
    for excluded in BUSINESS_EXCLUSIONS:
        if name == excluded or name.startswith(excluded + " "):
            return excluded
    return None


def parse_amount(value):
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if text.startswith("$"):
            text = text[1:].strip()
    else:
        text = str(value)
    try:
        amount = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("transaction_amount must be a decimal number") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("transaction_amount must be a finite nonnegative amount")
    return amount


def parse_stored_points(value):
    if value is None:
        return None
    match = re.fullmatch(r"\s*(-?\d+)\s*(?:points?)?\s*", str(value), re.I)
    if not match:
        raise ValueError("rewards_earned must be a whole point count")
    return int(match.group(1))


def floor_points(amount, rate_percent):
    return int((amount * rate_percent).to_integral_value(rounding=ROUND_FLOOR))


def analyze_one(txn):
    result = {
        "transaction_id": txn.get("transaction_id"),
        "credit_card_type": txn.get("credit_card_type"),
        "review_status": "needs_manual_review",
        "expected_points": None,
        "stored_points": None,
        "base_rate_percent": None,
        "promo_multiplier": None,
        "effective_rate_percent": None,
        "exclusion": None,
        "rationale": [],
    }
    try:
        card = txn.get("credit_card_type")
        status = normalized(txn.get("status", ""))
        if status != "completed":
            result["rationale"].append(
                "Transaction is not COMPLETED/posted; final rewards cannot be calculated."
            )
            return result

        amount = parse_amount(txn.get("transaction_amount"))
        txn_date = parse_date(txn.get("transaction_date"), "transaction_date")
        result["stored_points"] = parse_stored_points(txn.get("rewards_earned"))
        category = normalized(txn.get("category", ""))
        is_bonus_category = category in {"travel", "software"}

        if card == SILVER_CARD:
            if not is_bonus_category:
                result["rationale"].append(
                    "No documented nonbonus rate is available for Silver Rewards Card; manual policy review is required."
                )
                return result
            base_rate = Decimal("4")
            multiplier = Decimal("1")
            result["rationale"].append(
                "Posted Travel/Software transaction uses the documented 4.0% Silver rate."
            )

        elif card == BUSINESS_CARD:
            excluded = is_excluded_merchant(txn.get("merchant_name", ""))
            if excluded:
                base_rate = Decimal("1")
                result["exclusion"] = excluded
                result["rationale"].append(
                    "Merchant matches a documented Business Silver exclusion and uses the 1.0% standard rate."
                )
            elif is_bonus_category:
                base_rate = Decimal("10")
                result["rationale"].append(
                    "Posted Travel/Software transaction uses the documented 10.0% Business Silver rate."
                )
            else:
                base_rate = Decimal("1")
                result["rationale"].append(
                    "Nonbonus Business Silver transaction uses the documented 1.0% standard rate."
                )

            opening = parse_date(txn.get("account_open_date"), "account_open_date")
            if txn_date < opening:
                result["rationale"].append(
                    "Transaction predates the account opening date; records require manual review."
                )
                return result

            eligible_opening = PROMO_START <= opening <= PROMO_END
            promo_end_exclusive = add_calendar_months(opening, 6)
            if eligible_opening and txn_date < promo_end_exclusive:
                multiplier = Decimal("2")
                result["rationale"].append(
                    "Eligible account is within its first six calendar months; double-cash-back multiplier applies."
                )
            else:
                multiplier = Decimal("1")
                if not eligible_opening:
                    result["rationale"].append(
                        "Account opening date is outside the documented promotion enrollment window."
                    )
                else:
                    result["rationale"].append(
                        "Transaction is outside the first six calendar months after account opening."
                    )
        else:
            result["rationale"].append("Card type is unsupported by this documented policy.")
            return result

        effective_rate = base_rate * multiplier
        expected = floor_points(amount, effective_rate)
        result.update({
            "expected_points": expected,
            "base_rate_percent": str(base_rate),
            "promo_multiplier": str(multiplier),
            "effective_rate_percent": str(effective_rate),
        })
        result["rationale"].append(
            "Expected points equal floor(transaction_amount × effective_rate_percent)."
        )
        if result["stored_points"] is None:
            result["review_status"] = "needs_manual_review"
            result["rationale"].append(
                "No parseable stored rewards value was supplied for comparison."
            )
        elif result["stored_points"] == expected:
            result["review_status"] = "matches_documented_policy"
        else:
            result["review_status"] = "discrepancy"
            result["point_difference"] = expected - result["stored_points"]
    except (ValueError, TypeError) as exc:
        result["rationale"].append(str(exc))
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        transactions = payload.get("transactions")
        if not isinstance(transactions, list):
            raise ValueError("Input must be an object with a transactions array")
        if not all(isinstance(txn, dict) for txn in transactions):
            raise ValueError("Each transactions entry must be an object")
        results = [analyze_one(txn) for txn in transactions]
        print(json.dumps({"results": results}, separators=(",", ":"), ensure_ascii=False))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")), file=sys.stdout)
        sys.exit(2)


if __name__ == "__main__":
    main()
