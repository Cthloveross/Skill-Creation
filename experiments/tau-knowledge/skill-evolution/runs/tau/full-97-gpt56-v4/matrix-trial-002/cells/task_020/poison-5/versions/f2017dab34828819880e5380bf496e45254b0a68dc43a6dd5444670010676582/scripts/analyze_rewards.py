#!/usr/bin/env python3
"""Assess documented cash-back rewards from JSON stdin and emit JSON stdout."""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

BUSINESS = "Business Silver Rewards Card"
SILVER = "Silver Rewards Card"
PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)
EXCLUSIONS = (
    "concur", "sap concur", "expensify", "navan", "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online", "coursera",
    "udemy", "linkedin learning", "skillshare", "pluralsight",
)


def fail(message):
    raise ValueError(message)


def parse_date(value, field):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        fail("%s must be an ISO YYYY-MM-DD date" % field)


def parse_decimal(value, field):
    if isinstance(value, str):
        value = value.strip().replace("$", "").replace(",", "")
        if value.lower().endswith("points"):
            value = value[:-6].strip()
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        fail("%s must be numeric" % field)
    if result < 0:
        fail("%s must not be negative" % field)
    return result


def add_months(d, count):
    month_number = d.month - 1 + count
    year = d.year + month_number // 12
    month = month_number % 12 + 1
    days_in_month = (date(year + (month == 12), 1 if month == 12 else month + 1, 1) - date(year, month, 1)).days
    return date(year, month, min(d.day, days_in_month))


def compact_decimal(value):
    value = value.normalize()
    text = format(value, "f")
    return "0" if text in ("-0", "") else text


def exclusion_name(merchant):
    normalized = " ".join(str(merchant or "").casefold().split())
    for excluded in EXCLUSIONS:
        if normalized == excluded or normalized.startswith(excluded + " ") or normalized.startswith(excluded + "-"):
            return excluded
    return None


def account_map(payload):
    raw = payload.get("accounts")
    if raw is None:
        raw = [payload.get("account")] if payload.get("account") is not None else []
    if not isinstance(raw, list) or not raw:
        fail("provide a nonempty accounts array or account object")
    result = {}
    for item in raw:
        if not isinstance(item, dict):
            fail("each account must be an object")
        card_type = item.get("card_type")
        opened = item.get("date_of_account_open")
        if not card_type or not opened:
            fail("each account requires card_type and date_of_account_open")
        if card_type in result:
            fail("duplicate card_type is ambiguous: %s" % card_type)
        result[card_type] = parse_date(opened, "date_of_account_open")
    return result


def point_round(value):
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def assess(transaction, opened_by_type):
    if not isinstance(transaction, dict):
        fail("each transaction must be an object")
    card_type = transaction.get("credit_card_type")
    if not card_type:
        fail("transaction missing credit_card_type")
    if card_type not in opened_by_type:
        fail("no account supplied for transaction card type: %s" % card_type)
    amount = parse_decimal(transaction.get("transaction_amount"), "transaction_amount")
    actual = parse_decimal(transaction.get("rewards_earned"), "rewards_earned")
    if actual != actual.to_integral_value():
        fail("rewards_earned must be a whole number of points")
    actual = int(actual)
    tx_date = parse_date(transaction.get("transaction_date"), "transaction_date")
    status = str(transaction.get("status", "")).upper()
    category = str(transaction.get("category", "")).casefold()
    merchant = str(transaction.get("merchant_name", ""))
    output = {
        "transaction_id": transaction.get("transaction_id"),
        "card_type": card_type,
        "merchant_name": merchant,
        "transaction_date": tx_date.isoformat(),
        "category": transaction.get("category"),
        "posted_status": status,
        "actual_points": actual,
    }
    if amount == 0:
        output.update({"status": "not_assessed", "reason": "Zero-value transaction cannot have a meaningful reward rate."})
        return output
    output["amount"] = format(amount.quantize(Decimal("0.01")), "f")
    output["actual_rate_percent"] = compact_decimal(Decimal(actual) / amount)
    if status != "COMPLETED":
        output.update({"status": "not_final", "reason": "Only completed/posted transactions are final for this comparison."})
        return output
    expected_rate = None
    reason = None
    if card_type == BUSINESS:
        excluded = exclusion_name(merchant)
        eligible_bonus = category in ("travel", "software") and excluded is None
        normal_rate = Decimal("10") if eligible_bonus else Decimal("1")
        opened = opened_by_type[card_type]
        promo_eligible = PROMO_START <= opened <= PROMO_END
        promo_active = promo_eligible and opened <= tx_date < add_months(opened, 6)
        expected_rate = normal_rate * (2 if promo_active else 1)
        if excluded:
            reason = "Named Business Silver exclusion (%s) uses the standard rate." % excluded
        elif eligible_bonus:
            reason = "Travel/Software merchant category qualifies for the Business Silver bonus rate."
        else:
            reason = "Non-Travel/Software category uses the Business Silver standard rate."
        if promo_active:
            reason += " The eligible first-six-calendar-month promotion doubles that rate."
    elif card_type == SILVER:
        if category in ("travel", "software"):
            expected_rate = Decimal("4")
            reason = "Travel/Software category is assessed at the Silver Rewards enhanced rate."
        else:
            output.update({"status": "outside_documented_rate_scope", "reason": "This Skill has no documented numerical Silver Rewards rate for this category."})
            return output
    else:
        output.update({"status": "unsupported_card", "reason": "This Skill documents only Business Silver and Silver Rewards rates."})
        return output
    expected = point_round(amount * expected_rate)  # 1 percentage point equals one point per dollar.
    difference = expected - actual
    output.update({
        "expected_rate_percent": compact_decimal(expected_rate),
        "expected_points": expected,
        "difference_points": difference,
        "status": "matches" if difference == 0 else ("possible_undercredit" if difference > 0 else "posted_above_calculated_rate"),
        "reason": reason,
    })
    return output


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            fail("input must be a JSON object")
        transactions = payload.get("transactions")
        if not isinstance(transactions, list):
            fail("transactions must be an array")
        opened_by_type = account_map(payload)
        assessments = [assess(tx, opened_by_type) for tx in transactions]
        undercredits = [a for a in assessments if a.get("status") == "possible_undercredit"]
        output = {
            "assessments": assessments,
            "summary": {
                "transaction_count": len(assessments),
                "assessed_count": sum(1 for a in assessments if "expected_points" in a),
                "matching_count": sum(1 for a in assessments if a.get("status") == "matches"),
                "possible_undercredit_count": len(undercredits),
                "total_missing_points": sum(a["difference_points"] for a in undercredits),
            },
        }
        print(json.dumps(output, indent=2, sort_keys=True))
    except (ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
