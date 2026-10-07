#!/usr/bin/env python3
"""Audit Silver and Business Silver rewards.

Read the SKILL.md JSON schema from stdin and write a JSON audit report to stdout.
No external dependencies are required.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

PERSONAL = "Silver Rewards Card"
BUSINESS = "Business Silver Rewards Card"
BONUS_CATEGORIES = {"travel", "software"}
BUSINESS_EXCLUSIONS = {
    "concur", "sap concur", "expensify", "navan", "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online", "coursera",
    "udemy", "linkedin learning", "skillshare", "pluralsight",
}
PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be YYYY-MM-DD")
    return date.fromisoformat(value)


def six_month_anniversary(start):
    """Return the same day six calendar months later, clamped to month length."""
    month_index = start.month - 1 + 6
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    import calendar
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def decimal_amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("transaction_amount is not a decimal")
    if amount < 0:
        raise ValueError("transaction_amount cannot be negative")
    return amount


def whole_points(amount, rate):
    return int((amount * rate * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def normalized(value):
    return " ".join(str(value or "").casefold().split())


def merchant_is_excluded(merchant):
    name = normalized(merchant)
    # Merchant records frequently include a product suffix (for example, a suite name).
    return any(name == exclusion or name.startswith(exclusion + " ") for exclusion in BUSINESS_EXCLUSIONS)


def cents(points):
    return format((Decimal(points) / Decimal("100")).quantize(Decimal("0.01")), "f")


def rate_for(card_type, category, merchant, txn_date, opened):
    category_is_bonus = normalized(category) in BONUS_CATEGORIES
    if card_type == PERSONAL:
        rate = Decimal("0.04") if category_is_bonus else Decimal("0.01")
        return rate, "personal bonus category" if category_is_bonus else "personal standard category", False

    excluded = merchant_is_excluded(merchant)
    base = Decimal("0.10") if category_is_bonus and not excluded else Decimal("0.01")
    reason = "business bonus category" if category_is_bonus and not excluded else "business standard category"
    if excluded:
        reason = "business merchant exclusion (standard rate)"
    promo_eligible = opened is not None and PROMO_START <= opened <= PROMO_END
    in_promo_window = promo_eligible and opened <= txn_date < six_month_anniversary(opened)
    if in_promo_window:
        return base * Decimal("2"), reason + "; double-cash-back promotional window", True
    return base, reason, False


def main(payload):
    accounts = payload.get("accounts", [])
    transactions = payload.get("transactions", [])
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        raise ValueError("accounts and transactions must be arrays")

    open_dates = {}
    for account in accounts:
        if not isinstance(account, dict):
            continue
        card = account.get("card_type")
        if card in (PERSONAL, BUSINESS):
            try:
                open_dates[card] = parse_date(account.get("date_of_account_open"))
            except (ValueError, TypeError):
                open_dates[card] = None

    report = {"point_to_cash_dollars": "0.01", "cards": [], "review_items": [], "unreviewed": []}
    card_results = {card: [] for card in (PERSONAL, BUSINESS)}

    for index, txn in enumerate(transactions):
        label = txn.get("transaction_id", "transaction at index %d" % index) if isinstance(txn, dict) else "transaction at index %d" % index
        if not isinstance(txn, dict):
            report["unreviewed"].append({"transaction": label, "reason": "transaction record is not an object"})
            continue
        card = txn.get("credit_card_type")
        if card not in (PERSONAL, BUSINESS):
            report["unreviewed"].append({"transaction": label, "reason": "unsupported or missing card type"})
            continue
        if normalized(txn.get("status")) != "completed":
            report["unreviewed"].append({"transaction": label, "reason": "transaction is not completed/posted"})
            continue
        try:
            txn_date = parse_date(txn.get("transaction_date"))
            amount = decimal_amount(txn.get("transaction_amount"))
            awarded = int(Decimal(str(txn.get("rewards_earned"))))
            if awarded < 0:
                raise ValueError("rewards_earned cannot be negative")
        except (ValueError, TypeError, InvalidOperation) as exc:
            report["unreviewed"].append({"transaction": label, "reason": "malformed transaction: " + str(exc)})
            continue
        if not normalized(txn.get("category")):
            report["unreviewed"].append({"transaction": label, "reason": "missing merchant category; bonus eligibility cannot be confirmed"})
            continue
        rate, explanation, promo_applied = rate_for(card, txn.get("category"), txn.get("merchant_name"), txn_date, open_dates.get(card))
        expected = whole_points(amount, rate)
        item = {
            "transaction_id": txn.get("transaction_id"), "card_type": card,
            "transaction_date": txn_date.isoformat(), "merchant_name": txn.get("merchant_name"),
            "category": txn.get("category"), "amount_dollars": format(amount.quantize(Decimal("0.01")), "f"),
            "rate_percent": format(rate * 100, "f"), "rate_explanation": explanation,
            "promo_applied": promo_applied, "expected_points": expected,
            "expected_cash_dollars": cents(expected), "awarded_points": awarded,
            "awarded_cash_dollars": cents(awarded), "delta_points": awarded - expected,
            "delta_cash_dollars": cents(awarded - expected),
        }
        card_results[card].append(item)
        if item["delta_points"] != 0:
            report["review_items"].append(item)

    for card in (PERSONAL, BUSINESS):
        items = card_results[card]
        if not items and card not in open_dates:
            continue
        report["cards"].append({
            "card_type": card,
            "account_open_date": open_dates[card].isoformat() if open_dates.get(card) else None,
            "transactions": items,
            "completed_transaction_count": len(items),
            "expected_points_total": sum(x["expected_points"] for x in items),
            "awarded_points_total": sum(x["awarded_points"] for x in items),
            "delta_points_total": sum(x["delta_points"] for x in items),
        })
    return report


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), indent=2, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
