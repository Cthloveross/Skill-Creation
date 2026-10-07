#!/usr/bin/env python3
"""Audit posted rewards for Business Silver and consumer Silver cards.

Input and output are JSON objects on stdin/stdout. See SKILL.md for schema.
"""
import calendar
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

BUSINESS = "Business Silver Rewards Card"
CONSUMER = "Silver Rewards Card"
PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)
QUALIFYING_CATEGORIES = {"travel", "software"}
EXCLUSIONS = (
    "concur", "sap concur", "expensify", "navan",
    "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online",
    "coursera", "udemy", "linkedin learning", "skillshare", "pluralsight",
)


def pick(record, *names):
    for name in names:
        if name in record and record[name] is not None:
            return record[name]
    return None


def parse_date(value):
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def parse_decimal(value):
    text = str(value).strip().replace("$", "").replace(",", "")
    return Decimal(text)


def parse_points(value):
    if isinstance(value, str):
        value = value.strip().replace("points", "").replace("point", "").strip()
    return Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def merchant_is_excluded(merchant):
    normalized = " ".join(str(merchant or "").casefold().split())
    # A listed merchant followed by a product descriptor is still that merchant.
    return any(normalized == name or normalized.startswith(name + " ") for name in EXCLUSIONS)


def points_for(amount, rate):
    return (amount * rate * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def money_for_points(points):
    return (points / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def json_decimal(value):
    # JSON numbers are emitted as strings to avoid binary rounding ambiguity.
    return format(value, "f")


def fail(message):
    print(json.dumps({"error": message}, indent=2))
    raise SystemExit(2)


def main(payload):
    if not isinstance(payload, dict):
        fail("input must be a JSON object")
    accounts = payload.get("accounts")
    transactions = payload.get("transactions")
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        fail("accounts and transactions must both be arrays")

    opening_dates = {}
    account_warnings = []
    for account in accounts:
        if not isinstance(account, dict):
            account_warnings.append("ignored a non-object account record")
            continue
        card_type = pick(account, "card_type", "credit_card_type")
        opening = pick(account, "date_of_account_open", "account_open_date")
        if card_type is None or opening is None:
            continue
        try:
            opening_dates.setdefault(str(card_type), []).append(parse_date(opening))
        except (ValueError, TypeError):
            account_warnings.append("ignored an account with an invalid opening date")

    findings, anomalies, skipped, unsupported = [], [], [], []
    for index, txn in enumerate(transactions):
        label = "transaction at index %d" % index
        if not isinstance(txn, dict):
            unsupported.append({"transaction": label, "reason": "transaction is not an object"})
            continue
        txn_id = pick(txn, "transaction_id", "id") or label
        card_type = pick(txn, "credit_card_type", "card_type")
        status = str(pick(txn, "status") or "").upper()
        if status != "COMPLETED":
            skipped.append({"transaction_id": str(txn_id), "status": status or None,
                            "reason": "only completed/posted transactions are audited"})
            continue
        if card_type not in (BUSINESS, CONSUMER):
            unsupported.append({"transaction_id": str(txn_id), "reason": "unsupported or missing card type"})
            continue
        try:
            amount = parse_decimal(pick(txn, "transaction_amount", "amount"))
            txn_date = parse_date(pick(txn, "transaction_date", "date"))
            actual = parse_points(pick(txn, "rewards_earned", "actual_points"))
        except (InvalidOperation, ValueError, TypeError):
            unsupported.append({"transaction_id": str(txn_id),
                                "reason": "missing or invalid amount, date, or recorded points"})
            continue
        if amount < 0:
            unsupported.append({"transaction_id": str(txn_id), "reason": "negative amount requires credit/refund handling"})
            continue

        category = " ".join(str(pick(txn, "category") or "").casefold().split())
        merchant = str(pick(txn, "merchant_name", "merchant") or "")
        is_qualifying_category = category in QUALIFYING_CATEGORIES
        excluded = merchant_is_excluded(merchant)
        promotion_applied = False
        opening_date = None

        if card_type == BUSINESS:
            direct_opening = pick(txn, "account_open_date", "date_of_account_open")
            try:
                if direct_opening is not None:
                    opening_date = parse_date(direct_opening)
                else:
                    candidates = opening_dates.get(BUSINESS, [])
                    if len(candidates) == 1:
                        opening_date = candidates[0]
                    elif len(candidates) > 1:
                        raise LookupError("multiple Business Silver accounts")
                if opening_date is None:
                    raise LookupError("no Business Silver opening date")
            except (ValueError, TypeError, LookupError) as exc:
                unsupported.append({"transaction_id": str(txn_id),
                                    "reason": "cannot determine Business Silver promotional eligibility: " + str(exc)})
                continue
            qualifies_for_offer = PROMO_START <= opening_date <= PROMO_END
            promotion_applied = (qualifies_for_offer and txn_date >= opening_date
                                 and txn_date < add_months(opening_date, 6))
            base_rate = Decimal("0.10") if is_qualifying_category and not excluded else Decimal("0.01")
            rate = base_rate * (Decimal("2") if promotion_applied else Decimal("1"))
        else:
            base_rate = Decimal("0.04") if is_qualifying_category else Decimal("0.01")
            rate = base_rate

        expected = points_for(amount, rate)
        difference = actual - expected
        finding = {
            "transaction_id": str(txn_id),
            "card_type": card_type,
            "merchant_name": merchant or None,
            "transaction_date": txn_date.isoformat(),
            "posted_category": category or None,
            "amount_dollars": json_decimal(amount.quantize(Decimal("0.01"))),
            "excluded_merchant": excluded if card_type == BUSINESS else False,
            "promotion_applied": promotion_applied,
            "rate_percent": json_decimal(rate * Decimal("100")),
            "actual_points": int(actual),
            "actual_cash_value_dollars": json_decimal(money_for_points(actual)),
            "expected_points": int(expected),
            "expected_cash_value_dollars": json_decimal(money_for_points(expected)),
            "difference_points": int(difference),
            "difference_cash_value_dollars": json_decimal(money_for_points(difference)),
        }
        findings.append(finding)
        if difference != 0:
            anomalies.append(finding)

    total_difference = sum((Decimal(item["difference_points"]) for item in findings), Decimal("0"))
    output = {
        "findings": findings,
        "anomalies": anomalies,
        "skipped": skipped,
        "unsupported": unsupported,
        "warnings": account_warnings,
        "summary": {
            "input_transactions": len(transactions),
            "auditable_completed_transactions": len(findings),
            "anomaly_count": len(anomalies),
            "skipped_count": len(skipped),
            "unsupported_count": len(unsupported),
            "total_difference_points": int(total_difference),
            "total_difference_cash_value_dollars": json_decimal(money_for_points(total_difference)),
        },
    }
    print(json.dumps(output, indent=2, sort_keys=False))


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail("invalid JSON input: " + str(exc))
    main(incoming)
