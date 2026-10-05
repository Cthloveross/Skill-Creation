#!/usr/bin/env python3
"""Calculate Platinum Rewards annual-fee rebate eligibility from JSON stdin."""

import calendar
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
DEFAULT_THRESHOLD = Decimal("7500.00")
DEFAULT_REBATE = Decimal("150.00")


def parse_date(value):
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("unsupported date format: %r" % value)


def parse_money(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("money value is required")
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    if not isinstance(value, str):
        raise ValueError("unsupported money value")
    text = value.strip()
    negative = text.startswith("(") and text.endswith(")")
    text = text.replace("$", "").replace(",", "").replace("(", "").replace(")", "")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("invalid money value: %r" % value) from exc
    if negative:
        amount = -amount
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def add_months(anchor, months):
    """Add calendar months while retaining the anniversary day where possible."""
    index = anchor.month - 1 + months
    year = anchor.year + index // 12
    month = index % 12 + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def field(record, *names):
    for name in names:
        if name in record and record[name] not in (None, ""):
            return record[name]
    return None


def text(record, *names):
    value = field(record, *names)
    return "" if value is None else str(value).lower()


def classify_transaction(record):
    """Return (included, signed_amount, reason)."""
    if record.get("eligible") is False:
        return False, Decimal("0.00"), "explicitly_ineligible"

    status = text(record, "status")
    if any(word in status for word in ("pending", "declined", "reversed", "void")):
        return False, Decimal("0.00"), "not_posted_or_reversed"
    if "disput" in status and not any(word in status for word in ("resolved", "closed")):
        return False, Decimal("0.00"), "unresolved_dispute"

    classification = " ".join((
        text(record, "category"),
        text(record, "transaction_type", "type", "description"),
    ))
    exclusions = (
        "fee", "interest", "cash advance", "cash-equivalent", "cash equivalent",
        "money order", "traveler", "balance transfer", "person-to-person", "p2p",
        "funding transaction",
    )
    if any(term in classification for term in exclusions):
        return False, Decimal("0.00"), "excluded_transaction_type"

    amount = parse_money(field(record, "amount", "transaction_amount"))
    # A refund/return/credit is a reduction even if the source encodes it positive.
    if any(term in classification for term in ("refund", "return", "credit", "adjustment")):
        amount = -abs(amount)
    return True, amount, "eligible_posted_purchase_or_credit"


def evaluate(data):
    required = ("account_open_date", "as_of_date", "first_year_fee_waived", "history_complete", "transactions")
    missing = [name for name in required if name not in data]
    if missing:
        raise ValueError("missing required field(s): " + ", ".join(missing))
    if not isinstance(data["first_year_fee_waived"], bool):
        raise ValueError("first_year_fee_waived must be boolean")
    if not isinstance(data["history_complete"], bool):
        raise ValueError("history_complete must be boolean")
    if not isinstance(data["transactions"], list):
        raise ValueError("transactions must be an array")

    opened = parse_date(data["account_open_date"])
    as_of = parse_date(data["as_of_date"])
    if as_of < opened:
        raise ValueError("as_of_date precedes account_open_date")
    threshold = parse_money(data.get("threshold", DEFAULT_THRESHOLD))
    rebate = parse_money(data.get("rebate_amount", DEFAULT_REBATE))
    if threshold < 0 or rebate < 0:
        raise ValueError("threshold and rebate_amount cannot be negative")

    first_eligible_start = add_months(opened, 12 if data["first_year_fee_waived"] else 0)
    year_start = first_eligible_start
    latest_start = None
    # A cardmember year ending at its next anniversary is closed on that anniversary.
    while add_months(year_start, 12) <= as_of:
        latest_start = year_start
        year_start = add_months(year_start, 12)

    base = {
        "threshold": money(threshold),
        "rebate_amount": money(rebate),
        "account_open_date": opened.isoformat(),
        "as_of_date": as_of.isoformat(),
        "first_year_fee_waived": data["first_year_fee_waived"],
        "history_complete": data["history_complete"],
    }
    if latest_start is None:
        base.update({
            "evaluation_available": False,
            "spend_result": "not_yet_evaluable",
            "rebate_result": "not_yet_evaluable",
            "message": "No fee-eligible cardmember year of 12 fully closed anniversary windows is available as of the review date.",
            "windows": [],
        })
        return base

    windows = []
    for index in range(12):
        start = add_months(latest_start, index)
        next_start = add_months(latest_start, index + 1)
        windows.append({
            "number": index + 1,
            "start_date": start,
            "end_date": date.fromordinal(next_start.toordinal() - 1),
            "net_eligible_spend": Decimal("0.00"),
            "included_transaction_count": 0,
            "excluded_transaction_count": 0,
            "excluded_reasons": {},
        })

    malformed = []
    for position, record in enumerate(data["transactions"]):
        if not isinstance(record, dict):
            malformed.append({"index": position, "reason": "record_is_not_an_object"})
            continue
        raw_date = field(record, "posted_date", "date_posted", "transaction_date")
        raw_amount = field(record, "amount", "transaction_amount")
        try:
            posted = parse_date(raw_date)
            if raw_amount is None:
                raise ValueError("missing amount")
        except ValueError as exc:
            malformed.append({"index": position, "transaction_id": record.get("transaction_id"), "reason": str(exc)})
            continue
        target = next((w for w in windows if w["start_date"] <= posted <= w["end_date"]), None)
        if target is None:
            continue
        try:
            included, amount, reason = classify_transaction(record)
        except ValueError as exc:
            malformed.append({"index": position, "transaction_id": record.get("transaction_id"), "reason": str(exc)})
            continue
        if included:
            target["net_eligible_spend"] += amount
            target["included_transaction_count"] += 1
        else:
            target["excluded_transaction_count"] += 1
            target["excluded_reasons"][reason] = target["excluded_reasons"].get(reason, 0) + 1

    window_output = []
    all_thresholds_met = True
    for window in windows:
        total = window["net_eligible_spend"].quantize(CENT)
        meets = total >= threshold
        all_thresholds_met = all_thresholds_met and meets
        window_output.append({
            "number": window["number"],
            "start_date": window["start_date"].isoformat(),
            "end_date": window["end_date"].isoformat(),
            "net_eligible_spend": money(total),
            "amount_above_or_below_threshold": money(total - threshold),
            "meets_threshold": meets,
            "included_transaction_count": window["included_transaction_count"],
            "excluded_transaction_count": window["excluded_transaction_count"],
            "excluded_reasons": window["excluded_reasons"],
        })

    if not data["history_complete"] or malformed:
        spend_result = "indeterminate"
    elif all_thresholds_met:
        spend_result = "qualified"
    else:
        spend_result = "not_qualified"

    if spend_result != "qualified":
        rebate_result = spend_result
    elif data.get("fee_billed") is False:
        rebate_result = "ineligible_fee_not_billed"
    elif data.get("account_active") is False:
        rebate_result = "ineligible_account_closed_or_product_changed"
    elif data.get("fee_billed") is True and data.get("account_active") is True:
        rebate_result = "eligible"
    else:
        rebate_result = "qualified_pending_fee_billing_confirmation"

    base.update({
        "evaluation_available": True,
        "evaluated_cardmember_year_start": latest_start.isoformat(),
        "evaluated_cardmember_year_end": date.fromordinal(add_months(latest_start, 12).toordinal() - 1).isoformat(),
        "spend_result": spend_result,
        "rebate_result": rebate_result,
        "failing_window_numbers": [w["number"] for w in window_output if not w["meets_threshold"]],
        "malformed_transaction_records": malformed,
        "windows": window_output,
    })
    return base


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(evaluate(data), indent=2, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc), "evaluation_available": False}, sort_keys=True))
        sys.exit(2)


if __name__ == "__main__":
    main()
