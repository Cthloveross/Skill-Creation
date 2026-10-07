#!/usr/bin/env python3
"""Deterministically audit credit-card transaction rewards.

Reads the JSON schema documented in SKILL.md from stdin and emits JSON only.
No external dependencies, file reads, network calls, or banking actions are used.
"""
import calendar
import json
import re
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

CARD_DIAMOND = "Diamond Elite Card"
CARD_BPLAT = "Business Platinum Rewards Card"
CARD_BSILVER = "Business Silver Rewards Card"
CARD_ECO = "EcoCard"
SUPPORTED = {CARD_DIAMOND, CARD_BPLAT, CARD_BSILVER, CARD_ECO}

SILVER_EXCLUSIONS = (
    "concur", "sap concur", "expensify", "navan", "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online", "coursera",
    "udemy", "linkedin learning", "skillshare", "pluralsight",
)
ECO_STANDARD_MERCHANTS = ("target", "walmart", "amazon", "thredup")
POSTED = {"completed", "posted"}
REVERSAL = {"returned", "refunded", "return", "refund"}
NON_POSTED = {"pending", "declined", "cancelled", "canceled", "failed", "reversed", "voided"}
ZERO_CATEGORIES = {"cash equivalent", "cash equivalents", "balance transfer", "balance transfers", "fee", "fees"}


def text(value):
    return "" if value is None else str(value).strip()


def norm(value):
    return re.sub(r"\s+", " ", text(value).casefold())


def parse_money(value):
    if isinstance(value, bool):
        raise ValueError("amount must not be boolean")
    cleaned = text(value).replace("$", "").replace(",", "")
    if not cleaned:
        raise ValueError("amount is required")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("invalid amount") from exc


def parse_points(value):
    if isinstance(value, bool):
        raise ValueError("rewards_earned must not be boolean")
    cleaned = re.sub(r"(?i)\s*points?\s*$", "", text(value)).replace(",", "")
    if not cleaned:
        raise ValueError("rewards_earned is required")
    try:
        parsed = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("invalid rewards_earned") from exc
    if parsed != parsed.to_integral_value():
        raise ValueError("rewards_earned must be a whole-point value")
    return int(parsed)


def parse_date(value):
    value = text(value)
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("date must use MM/DD/YYYY or YYYY-MM-DD")


def add_months(start, months):
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def contains_any(merchant, phrases):
    merchant = norm(merchant)
    return any(phrase in merchant for phrase in phrases)


def truth_flag(record, name):
    """Return optional authoritative boolean; reject non-booleans."""
    if name not in record or record[name] is None:
        return None
    if not isinstance(record[name], bool):
        raise ValueError(f"{name} must be boolean when supplied")
    return record[name]


def floor_points(amount, points_per_dollar, sign):
    # The documented rule is floor/truncate positive earned points. For a return,
    # calculate the original positive award then reverse it, avoiding a negative
    # mathematical floor that would over-reverse fractional points.
    earned = (abs(amount) * Decimal(str(points_per_dollar))).to_integral_value(rounding=ROUND_FLOOR)
    return int(earned) * sign


def account_open_dates(accounts):
    result = {}
    errors = []
    if not isinstance(accounts, list):
        return result, ["accounts must be an array"]
    for i, account in enumerate(accounts):
        if not isinstance(account, dict):
            errors.append(f"accounts[{i}] must be an object")
            continue
        card = text(account.get("card_type"))
        opened = account.get("date_of_account_open")
        if card and opened:
            try:
                result[card] = parse_date(opened)
            except ValueError as exc:
                errors.append(f"accounts[{i}].date_of_account_open: {exc}")
    return result, errors


def calculate(record, opens):
    required = ("transaction_id", "credit_card_type", "transaction_amount", "transaction_date", "merchant_name", "category", "status", "rewards_earned")
    missing = [field for field in required if not text(record.get(field))]
    if missing:
        return None, "missing required field(s): " + ", ".join(missing)
    card = text(record["credit_card_type"])
    if card not in SUPPORTED:
        return None, f"unsupported card type: {card}"
    try:
        amount = parse_money(record["transaction_amount"])
        recorded = parse_points(record["rewards_earned"])
        txn_date = parse_date(record["transaction_date"])
        category_ok = truth_flag(record, "merchant_category_eligible")
        green_ok = truth_flag(record, "green_eligible")
    except ValueError as exc:
        return None, str(exc)

    status = norm(record["status"])
    if status in NON_POSTED:
        return None, f"not posted (status: {text(record['status'])})"
    if status not in POSTED and status not in REVERSAL:
        return None, f"unsupported or unknown transaction status: {text(record['status'])}"
    sign = -1 if status in REVERSAL or amount < 0 else 1
    category = norm(record["category"])
    merchant = text(record["merchant_name"])
    basis = []

    if category in ZERO_CATEGORIES:
        rate = Decimal("0")
        basis.append("non-earning transaction category")
    elif card == CARD_DIAMOND:
        rate = Decimal("5")
        basis.append("Diamond Elite eligible-purchase rate: 5 points per dollar")
    elif card == CARD_BPLAT:
        enhanced_category = category in {"travel", "software", "media", "media advertising", "advertising"}
        enhanced = enhanced_category and category_ok is not False
        rate = Decimal("4") if enhanced else Decimal("1.5")
        basis.append("Business Platinum enhanced category" if enhanced else "Business Platinum standard category rate")
        if category_ok is False:
            basis.append("merchant-category eligibility override is false")
    elif card == CARD_BSILVER:
        opened = opens.get(CARD_BSILVER)
        if opened is None:
            return None, "Business Silver account-opening date is required to evaluate the promotion"
        excluded = contains_any(merchant, SILVER_EXCLUSIONS)
        enhanced_category = category in {"travel", "software"}
        enhanced = enhanced_category and not excluded and category_ok is not False
        rate = Decimal("10") if enhanced else Decimal("1")
        if excluded:
            basis.append("Business Silver named merchant exclusion: standard rate")
        elif enhanced:
            basis.append("Business Silver eligible travel/software rate")
        else:
            basis.append("Business Silver standard rate")
        if category_ok is False:
            basis.append("merchant-category eligibility override is false")
        promo_start, promo_end = date(2024, 11, 14), date(2025, 11, 14)
        eligible_opening = promo_start <= opened <= promo_end
        promo_active = eligible_opening and opened <= txn_date < add_months(opened, 6)
        if promo_active:
            rate *= 2
            basis.append("eligible first-six-calendar-month double-cash-back promotion")
        elif eligible_opening:
            basis.append("outside the account's first six calendar months; no promotion")
        else:
            basis.append("account opening outside promotion window; no promotion")
    else:  # EcoCard
        excluded = contains_any(merchant, ECO_STANDARD_MERCHANTS)
        category_green = category == "green"
        green = (green_ok if green_ok is not None else category_green)
        if excluded:
            green = False
            basis.append("EcoCard named merchant exclusion: standard rate")
        if green:
            rate = Decimal("5")
            basis.append("EcoCard qualifying green rate")
        else:
            rate = Decimal("1")
            basis.append("EcoCard standard rate")
        if green_ok is False:
            basis.append("green eligibility override is false")

    expected = floor_points(amount, rate, sign)
    difference = expected - recorded
    result = {
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
    }
    return result, None


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"input_errors": [f"invalid JSON input: {exc}"], "summary": {}, "findings": [], "audited": [], "not_audited": []}))
        return
    if not isinstance(payload, dict):
        print(json.dumps({"input_errors": ["top-level JSON value must be an object"], "summary": {}, "findings": [], "audited": [], "not_audited": []}))
        return

    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        print(json.dumps({"input_errors": ["transactions must be an array"], "summary": {}, "findings": [], "audited": [], "not_audited": []}))
        return
    opens, input_errors = account_open_dates(payload.get("accounts", []))
    audited, findings, skipped = [], [], []
    seen_ids = set()
    for index, record in enumerate(transactions):
        if not isinstance(record, dict):
            skipped.append({"input_index": index, "reason": "transaction must be an object"})
            continue
        txn_id = text(record.get("transaction_id"))
        if txn_id and txn_id in seen_ids:
            skipped.append({"transaction_id": txn_id, "input_index": index, "reason": "duplicate transaction_id"})
            continue
        if txn_id:
            seen_ids.add(txn_id)
        result, reason = calculate(record, opens)
        if reason:
            skipped.append({"transaction_id": txn_id or None, "input_index": index, "reason": reason})
            continue
        audited.append(result)
        if result["result"] == "mismatch":
            findings.append(result)

    total_delta = sum(item["difference_points"] for item in findings)
    output = {
        "input_errors": input_errors,
        "summary": {
            "transactions_received": len(transactions),
            "audited_count": len(audited),
            "not_audited_count": len(skipped),
            "mismatch_count": len(findings),
            "total_difference_points_for_mismatches": total_delta,
        },
        "findings": findings,
        "audited": audited,
        "not_audited": skipped,
    }
    print(json.dumps(output, indent=2, sort_keys=False))


if __name__ == "__main__":
    main()
