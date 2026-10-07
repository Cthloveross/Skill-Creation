#!/usr/bin/env python3
"""Deterministic credit-card reward audit.

Reads one JSON object from stdin and writes one JSON object to stdout. It has no
external dependencies and never performs banking actions.
"""
import calendar
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

DIAMOND = "Diamond Elite Card"
BPLAT = "Business Platinum Rewards Card"
BSILVER = "Business Silver Rewards Card"
ECO = "EcoCard"
SUPPORTED = {DIAMOND, BPLAT, BSILVER, ECO}
POSTED = {"completed", "posted"}
REVERSALS = {"returned", "refunded", "return", "refund"}
NON_POSTED = {"pending", "declined", "cancelled", "canceled", "failed", "reversed", "voided"}
ZERO_CATEGORIES = {"cash equivalent", "cash equivalents", "balance transfer", "balance transfers", "fee", "fees"}
SILVER_EXCLUSIONS = (
    "concur", "sap concur", "expensify", "navan", "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online", "coursera",
    "udemy", "linkedin learning", "skillshare", "pluralsight",
)
ECO_STANDARD_MERCHANTS = ("target", "walmart", "amazon", "thredup")


def text(value):
    return "" if value is None else str(value).strip()


def normalized(value):
    return re.sub(r"\s+", " ", text(value).casefold())


def parse_date(value):
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text(value), fmt).date()
        except ValueError:
            continue
    raise ValueError("date must use MM/DD/YYYY or YYYY-MM-DD")


def parse_amount(value):
    if isinstance(value, bool):
        raise ValueError("transaction_amount must not be boolean")
    cleaned = text(value).replace("$", "").replace(",", "")
    if not cleaned:
        raise ValueError("transaction_amount is required")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("invalid transaction_amount") from exc


def parse_points(value):
    if isinstance(value, bool):
        raise ValueError("rewards_earned must not be boolean")
    cleaned = re.sub(r"(?i)\s*points?\s*$", "", text(value)).replace(",", "")
    if not cleaned:
        raise ValueError("rewards_earned is required")
    try:
        result = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("invalid rewards_earned") from exc
    if result != result.to_integral_value():
        raise ValueError("rewards_earned must be a whole-point value")
    return int(result)


def optional_bool(record, field):
    if field not in record or record[field] is None:
        return None
    if not isinstance(record[field], bool):
        raise ValueError(field + " must be boolean when supplied")
    return record[field]


def add_months(start, months):
    index = start.month - 1 + months
    year, month = start.year + index // 12, index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def merchant_matches(merchant, names):
    value = normalized(merchant)
    return any(name in value for name in names)


def awarded_points(amount, rate, sign):
    """Floor the positive original award, then apply a refund/return reversal sign."""
    positive = (abs(amount) * rate).to_integral_value(rounding=ROUND_FLOOR)
    return int(positive) * sign


def read_open_dates(accounts):
    dates, errors = {}, []
    if not isinstance(accounts, list):
        return dates, ["accounts must be an array"]
    for i, account in enumerate(accounts):
        if not isinstance(account, dict):
            errors.append("accounts[%d] must be an object" % i)
            continue
        card, opened = text(account.get("card_type")), account.get("date_of_account_open")
        if card and opened:
            try:
                dates[card] = parse_date(opened)
            except ValueError as exc:
                errors.append("accounts[%d].date_of_account_open: %s" % (i, exc))
    return dates, errors


def calculate(record, opening_dates):
    required = (
        "transaction_id", "credit_card_type", "transaction_amount", "transaction_date",
        "merchant_name", "category", "status", "rewards_earned",
    )
    missing = [key for key in required if not text(record.get(key))]
    if missing:
        return None, "missing required field(s): " + ", ".join(missing)

    card = text(record["credit_card_type"])
    if card not in SUPPORTED:
        return None, "unsupported card type: " + card
    try:
        amount = parse_amount(record["transaction_amount"])
        recorded = parse_points(record["rewards_earned"])
        txn_date = parse_date(record["transaction_date"])
        category_override = optional_bool(record, "merchant_category_eligible")
        green_override = optional_bool(record, "green_eligible")
    except ValueError as exc:
        return None, str(exc)

    status = normalized(record["status"])
    if status in NON_POSTED:
        return None, "not posted (status: %s)" % text(record["status"])
    if status not in POSTED and status not in REVERSALS:
        return None, "unsupported or unknown transaction status: " + text(record["status"])

    category, merchant = normalized(record["category"]), text(record["merchant_name"])
    sign = -1 if status in REVERSALS or amount < 0 else 1
    basis = []

    if category in ZERO_CATEGORIES:
        rate = Decimal("0")
        basis.append("non-earning transaction category")
    elif card == DIAMOND:
        rate = Decimal("5")
        basis.append("Diamond Elite eligible-purchase rate: 5 points per dollar")
    elif card == BPLAT:
        enhanced = category in {"travel", "software", "media", "media advertising", "advertising"}
        enhanced = enhanced and category_override is not False
        rate = Decimal("4") if enhanced else Decimal("1.5")
        basis.append("Business Platinum enhanced category rate" if enhanced else "Business Platinum standard rate")
        if category_override is False:
            basis.append("merchant-category eligibility override is false")
    elif card == BSILVER:
        opened = opening_dates.get(BSILVER)
        if opened is None:
            return None, "Business Silver account-opening date is required to evaluate the promotion"
        excluded = merchant_matches(merchant, SILVER_EXCLUSIONS)
        enhanced = category in {"travel", "software"} and not excluded and category_override is not False
        rate = Decimal("10") if enhanced else Decimal("1")
        if excluded:
            basis.append("Business Silver named merchant exclusion: standard rate")
        else:
            basis.append("Business Silver eligible travel/software rate" if enhanced else "Business Silver standard rate")
        if category_override is False:
            basis.append("merchant-category eligibility override is false")
        promotion_window = date(2024, 11, 14) <= opened <= date(2025, 11, 14)
        promotion_active = promotion_window and opened <= txn_date < add_months(opened, 6)
        if promotion_active:
            rate *= 2
            basis.append("eligible first-six-calendar-month double-rewards promotion")
        elif promotion_window:
            basis.append("outside first six calendar months; no promotion")
        else:
            basis.append("account opening outside promotion window; no promotion")
    else:  # ECO
        excluded = merchant_matches(merchant, ECO_STANDARD_MERCHANTS)
        green = green_override if green_override is not None else category == "green"
        if excluded:
            green = False
            basis.append("EcoCard named merchant exclusion: standard rate")
        rate = Decimal("5") if green else Decimal("1")
        basis.append("EcoCard qualifying green rate" if green else "EcoCard standard rate")
        if green_override is False:
            basis.append("green eligibility override is false")

    expected = awarded_points(amount, rate, sign)
    difference = expected - recorded
    return {
        "transaction_id": text(record["transaction_id"]),
        "card_type": card,
        "transaction_date": txn_date.isoformat(),
        "merchant_name": merchant,
        "category": text(record["category"]),
        "status": text(record["status"]),
        "transaction_amount": format(amount, "f"),
        "recorded_points": recorded,
        "expected_points": expected,
        "difference_points": difference,
        "calculation_basis": basis,
        "result": "mismatch" if difference else "correct",
    }, None


def output_error(message):
    print(json.dumps({
        "input_errors": [message], "summary": {}, "findings": [],
        "audited": [], "not_audited": [],
    }))


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        output_error("invalid JSON input: %s" % exc)
        return
    if not isinstance(payload, dict):
        output_error("top-level JSON value must be an object")
        return
    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        output_error("transactions must be an array")
        return

    opening_dates, errors = read_open_dates(payload.get("accounts", []))
    audited, findings, not_audited, seen = [], [], [], set()
    for index, record in enumerate(transactions):
        if not isinstance(record, dict):
            not_audited.append({"input_index": index, "reason": "transaction must be an object"})
            continue
        transaction_id = text(record.get("transaction_id"))
        if transaction_id and transaction_id in seen:
            not_audited.append({"transaction_id": transaction_id, "input_index": index, "reason": "duplicate transaction_id"})
            continue
        if transaction_id:
            seen.add(transaction_id)
        result, reason = calculate(record, opening_dates)
        if reason:
            not_audited.append({"transaction_id": transaction_id or None, "input_index": index, "reason": reason})
            continue
        audited.append(result)
        if result["result"] == "mismatch":
            findings.append(result)

    # All customer-facing mismatch totals intentionally derive only from findings.
    under = sum(item["difference_points"] > 0 for item in findings)
    over = sum(item["difference_points"] < 0 for item in findings)
    mismatch_count = len(findings)
    correct_count = len(audited) - mismatch_count
    net_recorded_minus_expected = sum(-item["difference_points"] for item in findings)
    consistent = (
        under + over == mismatch_count
        and correct_count + mismatch_count == len(audited)
        and all(item["difference_points"] != 0 for item in findings)
    )
    summary = {
        "transactions_reviewed": len(transactions),
        "transactions_received": len(transactions),
        "audited_count": len(audited),
        "not_audited_count": len(not_audited),
        "correct_transactions": correct_count,
        "mismatches": mismatch_count,
        "mismatch_count": mismatch_count,
        "under_awarded_transactions": under,
        "over_awarded_transactions": over,
        "net_difference_points": net_recorded_minus_expected,
        "net_difference_explanation": "Negative means recorded points exceed calculated points.",
        "total_difference_points_for_mismatches": -net_recorded_minus_expected,
        "summary_consistent": consistent,
    }
    print(json.dumps({
        "input_errors": errors,
        "summary": summary,
        "findings": findings,
        "audited": audited,
        "not_audited": not_audited,
    }, indent=2))


if __name__ == "__main__":
    main()
