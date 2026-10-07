#!/usr/bin/env python3
"""Audit documented rewards rates. Reads one JSON object from stdin, emits JSON."""
import calendar
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

BUSINESS = "Business Silver Rewards Card"
SILVER = "Silver Rewards Card"
QUALIFYING = {"travel", "software"}
# Names are normalized and deliberately match the documented exclusion merchants.
EXCLUSIONS = {
    "concur", "sap concur", "expensify", "navan",
    "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online",
    "coursera", "udemy", "linkedin learning", "skillshare", "pluralsight",
}
PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a YYYY-MM-DD string")
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def add_months(d, months):
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def decimal_value(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} is required")
    text = str(value).replace("$", "").replace(",", "").strip()
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        raise ValueError(f"{field} is not numeric")
    try:
        return Decimal(match.group(0))
    except InvalidOperation as exc:
        raise ValueError(f"{field} is not numeric") from exc


def normalized(text):
    return " ".join(str(text or "").casefold().split())


def excluded_merchant(name):
    merchant = normalized(name)
    # Merchant records commonly include product suffixes (for example, a service name).
    return any(merchant == x or merchant.startswith(x + " ") for x in EXCLUSIONS)


def rounded_points(amount, rate):
    return int((amount * rate * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def account_openings(accounts):
    result = {}
    for a in accounts:
        if not isinstance(a, dict):
            continue
        card = a.get("card_type")
        try:
            opened = parse_date(a.get("date_of_account_open"))
        except (ValueError, TypeError):
            continue
        result.setdefault(card, []).append(opened)
    return result


def assess(tx, openings):
    out = {
        "transaction_id": tx.get("transaction_id"),
        "card_type": tx.get("credit_card_type"),
        "merchant_name": tx.get("merchant_name"),
        "transaction_date": tx.get("transaction_date"),
        "actual_points": None,
        "expected_points": None,
        "point_difference": None,
        "cash_difference": None,
        "rate_percent": None,
        "disposition": "not_assessable",
        "reason": None,
    }
    try:
        actual = decimal_value(tx.get("rewards_earned"), "rewards_earned")
        if actual != actual.to_integral_value():
            raise ValueError("rewards_earned must be whole points")
        out["actual_points"] = int(actual)
        amount = decimal_value(tx.get("transaction_amount"), "transaction_amount")
        if amount < 0:
            raise ValueError("transaction_amount cannot be negative")
        transaction_date = parse_date(tx.get("transaction_date"))
    except (ValueError, TypeError) as exc:
        out["reason"] = str(exc)
        return out

    if normalized(tx.get("status")) not in {"completed", "posted"}:
        out["reason"] = "Only completed/posted transactions are eligible for this audit."
        return out
    card = tx.get("credit_card_type")
    category = normalized(tx.get("category"))

    if card == BUSINESS:
        dates = openings.get(card, [])
        if len(dates) != 1:
            out["reason"] = "A single valid Business Silver account opening date is required."
            return out
        opened = dates[0]
        if transaction_date < opened:
            out["reason"] = "Transaction predates the supplied account opening date."
            return out
        qualifying = category in QUALIFYING and not excluded_merchant(tx.get("merchant_name"))
        base_rate = Decimal("0.10") if qualifying else Decimal("0.01")
        promo_eligible = PROMO_START <= opened <= PROMO_END
        in_six_months = opened <= transaction_date < add_months(opened, 6)
        multiplier = 2 if promo_eligible and in_six_months else 1
        rate = base_rate * multiplier
        if qualifying:
            reason = "Business Silver qualifying travel/software rate"
        elif excluded_merchant(tx.get("merchant_name")):
            reason = "Business Silver documented merchant exclusion uses the standard rate"
        else:
            reason = "Business Silver standard rate for non-qualifying purchases"
        if multiplier == 2:
            reason += "; eligible first-six-month double-cash-back promotion applied"

    elif card == SILVER:
        if category not in QUALIFYING:
            out["reason"] = "The supplied Silver Rewards terms establish a 4% rate only for travel/software; no base rate is inferred."
            return out
        rate = Decimal("0.04")
        reason = "Silver Rewards qualifying travel/software rate"
    else:
        out["reason"] = "Card product is not covered by this Skill's documented terms."
        return out

    expected = rounded_points(amount, rate)
    difference = expected - out["actual_points"]
    out.update({
        "expected_points": expected,
        "point_difference": difference,
        "cash_difference": format((Decimal(difference) / Decimal("100")).quantize(Decimal("0.01")), ".2f"),
        "rate_percent": format(rate * 100, "f"),
        "reason": reason,
        "disposition": "match" if difference == 0 else "mismatch",
    })
    return out


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        accounts = payload.get("accounts", [])
        transactions = payload.get("transactions", [])
        if not isinstance(accounts, list) or not isinstance(transactions, list):
            raise ValueError("accounts and transactions must be arrays")
        openings = account_openings(accounts)
        evaluations = [assess(tx, openings) if isinstance(tx, dict) else {
            "disposition": "not_assessable", "reason": "Transaction must be an object."
        } for tx in transactions]
        mismatches = [x for x in evaluations if x["disposition"] == "mismatch"]
        shortfall = sum(max(x["point_difference"], 0) for x in mismatches)
        overage = sum(max(-x["point_difference"], 0) for x in mismatches)
        output = {
            "as_of": payload.get("as_of"),
            "point_cash_conversion": "1 point = $0.01",
            "evaluations": evaluations,
            "summary": {
                "transactions_received": len(transactions),
                "assessed": sum(x["expected_points"] is not None for x in evaluations),
                "matches": sum(x["disposition"] == "match" for x in evaluations),
                "mismatches": len(mismatches),
                "not_assessable": sum(x["disposition"] == "not_assessable" for x in evaluations),
                "total_confirmed_shortfall_points": shortfall,
                "total_confirmed_shortfall_cash": format(Decimal(shortfall) / Decimal("100"), ".2f"),
                "total_confirmed_overage_points": overage,
                "total_confirmed_overage_cash": format(Decimal(overage) / Decimal("100"), ".2f"),
            },
        }
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
