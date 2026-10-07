#!/usr/bin/env python3
"""Compute a 12-window annual-fee rebate eligibility review from JSON stdin.

The program is deliberately read-only: it recommends no banking action and reports
when source data cannot support a determination.
"""
import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MONEY = Decimal("0.01")
EXCLUDED_TERMS = (
    "fee", "interest", "adjustment", "cash advance", "cash-equivalent",
    "cash equivalent", "balance transfer", "money order", "traveler",
    "person-to-person", "person to person", "p2p", "funding transfer",
)
POSTED_STATUSES = {"COMPLETED", "POSTED"}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return __import__("datetime").datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("unsupported date format: %r" % value)


def money(value):
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)
    if not isinstance(value, str):
        raise ValueError("transaction_amount must be numeric or a string")
    text = value.strip().replace("$", "").replace(",", "")
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return Decimal(text).quantize(MONEY, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError("invalid money value: %r" % value)


def fmt(value):
    return format(value.quantize(MONEY, rounding=ROUND_HALF_UP), ".2f")


def add_months_same_day(value, months):
    """Add calendar months only if the requested anniversary day exists.

    The supplied policy says 'same calendar day' but does not define a fallback for
    29th--31st anniversaries in shorter months. Rejecting those cases prevents an
    invented date rule from changing eligibility.
    """
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    try:
        return date(year, month, value.day)
    except ValueError:
        raise ValueError(
            "anniversary day %d does not exist in %04d-%02d; a documented "
            "short-month rule is required" % (value.day, year, month)
        )


def transaction_reason(tx):
    status = str(tx.get("status", "")).strip().upper()
    if status not in POSTED_STATUSES:
        return "not posted/completed (status=%s)" % (status or "missing")
    # Search common classifier fields. Merchant name alone is never used to infer type.
    classification = " ".join(
        str(tx.get(key, "")) for key in
        ("category", "transaction_type", "type", "subtype", "description")
    ).lower()
    if "dispute" in classification and "resolved" not in classification:
        return "unresolved disputed transaction"
    for term in EXCLUDED_TERMS:
        if term in classification:
            return "excluded %s" % term
    return None


def make_windows(start):
    windows = []
    for index in range(12):
        window_start = add_months_same_day(start, index)
        next_start = add_months_same_day(start, index + 1)
        windows.append({"index": index + 1, "start": window_start, "end": next_start,
                        "total": Decimal("0.00"), "included": 0})
    return windows


def latest_completed_start(first_fee_start, as_of):
    candidate = first_fee_start
    latest = None
    while True:
        end = add_months_same_day(candidate, 12)
        if end <= as_of:
            latest = candidate
            candidate = add_months_same_day(candidate, 12)
        else:
            return latest


def unavailable(message, warnings=None):
    return {
        "result": "unavailable", "message": message,
        "warnings": warnings or [], "windows": [], "failing_windows": [],
        "excluded_transactions": []
    }


def evaluate(data):
    try:
        opened = parse_date(data["account_open_date"])
        as_of = parse_date(data["as_of_date"])
        if as_of < opened:
            return unavailable("as_of_date is before account_open_date")
        threshold = money(data.get("threshold", "7500.00"))
        rebate = money(data.get("rebate_amount", "150.00"))
        if threshold < 0 or rebate < 0:
            return unavailable("threshold and rebate_amount must be nonnegative")
        if not isinstance(data.get("transactions", []), list):
            return unavailable("transactions must be a list")

        first_fee_start = add_months_same_day(
            opened, 12 if data.get("annual_fee_waived_first_year", False) else 0
        )
        override = data.get("evaluation_year_start")
        if override is not None:
            evaluation_start = parse_date(override)
            # It must be an annual anniversary from the first fee-billed year.
            cursor = first_fee_start
            valid = False
            while cursor <= evaluation_start:
                if cursor == evaluation_start:
                    valid = True
                    break
                cursor = add_months_same_day(cursor, 12)
            if not valid:
                return unavailable("evaluation_year_start is not a fee-billed annual anniversary")
        else:
            evaluation_start = latest_completed_start(first_fee_start, as_of)

        if evaluation_start is None:
            return {
                "result": "not_yet_complete",
                "message": "No fee-billed 12-month cardmember year has closed as of the supplied date.",
                "evaluation_year_start": None, "evaluation_year_end": None,
                "windows": [], "failing_windows": [], "excluded_transactions": [], "warnings": []
            }
        evaluation_end = add_months_same_day(evaluation_start, 12)
        if evaluation_end > as_of:
            return {
                "result": "not_yet_complete",
                "message": "The requested fee-billed cardmember year has not closed as of the supplied date.",
                "evaluation_year_start": evaluation_start.isoformat(),
                "evaluation_year_end": evaluation_end.isoformat(),
                "windows": [], "failing_windows": [], "excluded_transactions": [], "warnings": []
            }
        windows = make_windows(evaluation_start)
    except (KeyError, ValueError) as exc:
        return unavailable(str(exc))

    excluded = []
    warnings = []
    for position, tx in enumerate(data.get("transactions", [])):
        if not isinstance(tx, dict):
            warnings.append("transaction at index %d is not an object and was ignored" % position)
            continue
        try:
            posted = parse_date(tx.get("posting_date", tx.get("transaction_date")))
            amount = money(tx["transaction_amount"])
        except (KeyError, ValueError) as exc:
            warnings.append("transaction at index %d could not be read: %s" % (position, exc))
            continue
        if not (evaluation_start <= posted < evaluation_end):
            continue
        reason = transaction_reason(tx)
        tx_id = str(tx.get("transaction_id", tx.get("id", "index-%d" % position)))
        if reason:
            excluded.append({"transaction_id": tx_id, "posting_date": posted.isoformat(), "reason": reason})
            continue
        for window in windows:
            if window["start"] <= posted < window["end"]:
                window["total"] += amount
                window["included"] += 1
                break

    failing = []
    rendered_windows = []
    for window in windows:
        meets = window["total"] >= threshold
        item = {
            "window": window["index"], "start": window["start"].isoformat(),
            "end": (window["end"].fromordinal(window["end"].toordinal() - 1)).isoformat(),
            "net_eligible_posted_total": fmt(window["total"]),
            "threshold": fmt(threshold), "meets_threshold": meets,
            "included_transaction_count": window["included"]
        }
        rendered_windows.append(item)
        if not meets:
            failing.append(item)

    blocked = data.get("account_open") is False or data.get("product_changed") is True
    if blocked:
        result = "not_awardable"
        message = "The account was closed or product-changed before evaluation/posting, so the rebate cannot be awarded."
    elif failing:
        result = "not_qualified"
        message = "At least one monthly anniversary window did not meet the required threshold."
    else:
        result = "qualified"
        message = "All 12 completed monthly anniversary windows met the required threshold."

    return {
        "result": result, "message": message,
        "evaluation_year_start": evaluation_start.isoformat(),
        "evaluation_year_end": evaluation_end.isoformat(),
        "threshold": fmt(threshold), "rebate_amount": fmt(rebate),
        "windows": rendered_windows, "failing_windows": failing,
        "excluded_transactions": excluded, "warnings": warnings,
        "rebate_posting_status": "not_assessed"
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        output = evaluate(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        output = unavailable("invalid input: %s" % exc)
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
