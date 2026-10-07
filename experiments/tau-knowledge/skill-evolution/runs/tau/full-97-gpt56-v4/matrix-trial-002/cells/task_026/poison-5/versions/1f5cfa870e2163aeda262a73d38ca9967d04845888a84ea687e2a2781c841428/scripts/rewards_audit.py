#!/usr/bin/env python3
"""Read account and transaction JSON from stdin and emit a cash-back audit JSON."""
import calendar
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

BUSINESS = "Business Silver Rewards Card"
SILVER = "Silver Rewards Card"
PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)
EXCLUSIONS = (
    "concur", "sap concur", "expensify", "navan", "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online", "coursera",
    "udemy", "linkedin learning", "skillshare", "pluralsight",
)


def parse_date(value):
    """Parse dates emitted by banking tools or supplied in the documented schema."""
    if not isinstance(value, str):
        raise ValueError("date must be a YYYY-MM-DD or MM/DD/YYYY string")
    text = value.strip()
    for pattern in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    raise ValueError("date must be a YYYY-MM-DD or MM/DD/YYYY string")


def add_calendar_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def money(value):
    if isinstance(value, bool):
        raise ValueError("amount must not be boolean")
    text = str(value).strip().replace("$", "").replace(",", "")
    result = Decimal(text)
    if not result.is_finite():
        raise ValueError("amount must be finite")
    return result


def points(value):
    if isinstance(value, bool):
        raise ValueError("rewards must not be boolean")
    match = re.fullmatch(r"\s*(-?\d+)\s*(?:points?)?\s*", str(value).replace(",", ""), re.IGNORECASE)
    if not match:
        raise ValueError("rewards_earned must contain one whole point value")
    return int(match.group(1))


def norm(value):
    return re.sub(r"\s+", " ", str(value).strip().casefold())


def is_excluded_merchant(merchant):
    name = norm(merchant)
    # Source policy names specific merchants. A following space supports branded
    # variants such as a product name without treating unrelated words as matches.
    return any(name == item or name.startswith(item + " ") for item in EXCLUSIONS)


def category_eligible(category):
    return norm(category) in {"travel", "software", "saas", "software/saas"}


def whole_points(amount, rate):
    return int((amount * rate * Decimal("100")).to_integral_value(rounding=ROUND_FLOOR))


def audit_one(txn, openings):
    identifier = txn.get("transaction_id")
    result = {"transaction_id": identifier}
    required = ("credit_card_type", "merchant_name", "transaction_amount", "transaction_date", "category", "status", "rewards_earned")
    missing = [key for key in required if key not in txn]
    if missing:
        result.update(finding="unavailable", reason="missing required fields: " + ", ".join(missing))
        return result

    card = txn["credit_card_type"]
    if card not in (BUSINESS, SILVER):
        result.update(finding="unavailable", reason="unsupported card type")
        return result
    if not str(txn["merchant_name"]).strip():
        result.update(finding="unavailable", reason="merchant name is unavailable")
        return result
    category_text = norm(txn["category"])
    if not category_text or category_text in {"unknown", "n/a", "not available", "unavailable"}:
        result.update(finding="needs_review", reason="merchant category is unavailable or ambiguous")
        return result
    if card not in openings:
        result.update(finding="unavailable", reason="no unique account opening date for card type")
        return result
    if norm(txn["status"]) not in {"completed", "posted"}:
        result.update(finding="needs_review", reason="transaction is not posted/completed")
        return result

    try:
        amount = money(txn["transaction_amount"])
        txn_date = parse_date(txn["transaction_date"])
        open_date = openings[card]
        actual = points(txn["rewards_earned"])
    except (ValueError, InvalidOperation) as exc:
        result.update(finding="unavailable", reason=str(exc))
        return result
    if amount < 0:
        result.update(finding="needs_review", reason="negative amount/refund requires separate reversal review")
        return result
    if txn_date < open_date:
        result.update(finding="needs_review", reason="transaction predates the supplied account opening date")
        return result

    eligible = category_eligible(txn["category"])
    exclusion = card == BUSINESS and is_excluded_merchant(txn["merchant_name"])
    promo = False
    if card == BUSINESS:
        base_rate = Decimal("0.10") if eligible and not exclusion else Decimal("0.01")
        # The offer eligibility is based on opening within the stated offer dates;
        # its six-month window is measured from the opening date.
        promo = PROMO_START <= open_date <= PROMO_END and txn_date < add_calendar_months(open_date, 6)
        rate = base_rate * 2 if promo else base_rate
        if exclusion:
            rationale = "Business Silver named merchant exclusion; standard rate"
        elif eligible:
            rationale = "Business Silver eligible merchant category"
        else:
            rationale = "Business Silver non-eligible merchant category; standard rate"
    else:
        rate = Decimal("0.04") if eligible else Decimal("0.01")
        rationale = "Silver eligible merchant category" if eligible else "Silver non-eligible merchant category; standard rate"

    expected = whole_points(amount, rate)
    difference = expected - actual
    finding = "match" if difference == 0 else ("under_awarded" if difference > 0 else "over_awarded")
    result.update({
        "card_type": card,
        "actual_points": actual,
        "expected_points": expected,
        "difference_points": difference,
        "difference_cash_back_dollars": format(Decimal(difference) / Decimal("100"), ".2f"),
        "applied_rate_percent": format(rate * 100, "f"),
        "business_promo_applied": promo,
        "eligibility_rationale": rationale,
        "finding": finding,
    })
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        accounts = payload.get("accounts")
        transactions = payload.get("transactions")
        if not isinstance(accounts, list) or not isinstance(transactions, list):
            raise ValueError("accounts and transactions must be arrays")
        grouped = {}
        invalid_account_dates = 0
        for account in accounts:
            if not isinstance(account, dict) or "card_type" not in account or "date_of_account_open" not in account:
                continue
            card = account["card_type"]
            if card in (BUSINESS, SILVER):
                try:
                    grouped.setdefault(card, []).append(parse_date(account["date_of_account_open"]))
                except ValueError:
                    invalid_account_dates += 1
        openings = {card: dates[0] for card, dates in grouped.items() if len(dates) == 1}
        audits = [audit_one(txn, openings) if isinstance(txn, dict) else {
            "transaction_id": None, "finding": "unavailable", "reason": "transaction must be an object"
        } for txn in transactions]
        counts = {}
        for item in audits:
            counts[item["finding"]] = counts.get(item["finding"], 0) + 1
        summary = {"total_transactions": len(audits), "findings": counts}
        if invalid_account_dates:
            summary["invalid_account_dates"] = invalid_account_dates
        print(json.dumps({"audits": audits, "summary": summary}, indent=2))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
