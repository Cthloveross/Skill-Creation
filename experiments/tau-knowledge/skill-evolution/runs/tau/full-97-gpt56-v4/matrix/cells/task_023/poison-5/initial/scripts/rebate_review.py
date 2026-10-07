#!/usr/bin/env python3
"""Calculate a completed cardmember-year annual-fee rebate review.

Reads one JSON object from stdin and writes one JSON object to stdout.  It uses
only the Python standard library and intentionally never performs bank actions.
"""
from __future__ import annotations

import calendar
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

CENT = Decimal("0.01")


def parse_date(value: Any) -> date:
    """Parse ISO/MM-DD/YYYY-style input, accepting a timestamp after an ISO date."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    text = value.strip()
    if len(text) >= 10:
        candidate = text[:10]
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass
    for fmt in ("%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError("unsupported date format: %r" % value)


def add_months_same_day(value: date, months: int) -> date:
    """Add calendar months without inventing a rule for missing anniversary days."""
    index = value.year * 12 + (value.month - 1) + months
    year, zero_month = divmod(index, 12)
    month = zero_month + 1
    last_day = calendar.monthrange(year, month)[1]
    if value.day > last_day:
        raise ValueError(
            "monthly anniversary day %d does not exist in %04d-%02d; "
            "the applicable missing-day policy is required" % (value.day, year, month)
        )
    return date(year, month, value.day)


def parse_money(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("amount must not be boolean")
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        return Decimal(text).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise ValueError("invalid amount: %r" % value)


def money(value: Decimal) -> str:
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def emit_error(message: str) -> None:
    print(json.dumps({"ok": False, "error": message}, sort_keys=True))


def completed_cycle(opened: date, as_of: date) -> tuple[date, date] | None:
    """Return [start, end) for the latest completed 12-window year."""
    if as_of < opened:
        return None
    anchor = opened
    # The as-of anniversary begins a new window, so the preceding year closed
    # on the day before it and is eligible for evaluation.
    while True:
        next_anchor = add_months_same_day(anchor, 1)
        if next_anchor > as_of:
            break
        anchor = next_anchor
    months_elapsed = (anchor.year - opened.year) * 12 + anchor.month - opened.month
    if months_elapsed < 12:
        return None
    return add_months_same_day(anchor, -12), anchor


def main(payload: dict[str, Any]) -> dict[str, Any]:
    opened = parse_date(payload["account_open_date"])
    as_of = parse_date(payload["as_of_date"])
    threshold = parse_money(payload.get("threshold", "7500.00"))
    rebate = parse_money(payload.get("rebate_amount", "150.00"))
    if threshold < 0 or rebate < 0:
        raise ValueError("threshold and rebate_amount must be nonnegative")

    cycle = completed_cycle(opened, as_of)
    if cycle is None:
        return {
            "ok": True,
            "data_complete": True,
            "qualification_status": "no_completed_cardmember_year",
            "spend_requirement_met": None,
            "message": "No full 12-window cardmember year has completed as of the supplied date.",
            "account_open_date": opened.isoformat(),
            "as_of_date": as_of.isoformat(),
            "windows": [],
        }
    cycle_start, cycle_end = cycle
    boundaries = [add_months_same_day(cycle_start, n) for n in range(13)]
    totals = [Decimal("0.00") for _ in range(12)]
    issues: list[str] = []

    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        raise ValueError("transactions must be an array")
    for index, transaction in enumerate(transactions):
        if not isinstance(transaction, dict):
            issues.append("transaction %d is not an object" % index)
            continue
        try:
            posted = parse_date(transaction["posted_date"])
            amount = parse_money(transaction["amount"])
        except (KeyError, ValueError) as exc:
            issues.append("transaction %d cannot be evaluated: %s" % (index, exc))
            continue
        if not isinstance(transaction.get("eligible"), bool):
            issues.append("transaction %d lacks a boolean eligible classification" % index)
            continue
        if not transaction["eligible"]:
            continue
        if cycle_start <= posted < cycle_end:
            for window_index in range(12):
                if boundaries[window_index] <= posted < boundaries[window_index + 1]:
                    totals[window_index] += amount
                    break

    windows = []
    deficient = []
    for index, total in enumerate(totals):
        meets = total >= threshold
        record = {
            "window_number": index + 1,
            "start_date": boundaries[index].isoformat(),
            "end_date": (boundaries[index + 1]).isoformat(),
            "end_date_inclusive": (boundaries[index + 1]).fromordinal(boundaries[index + 1].toordinal() - 1).isoformat(),
            "eligible_net_purchase_total": money(total),
            "threshold": money(threshold),
            "meets_threshold": meets,
        }
        windows.append(record)
        if not meets:
            deficient.append(record)

    data_complete = not issues
    spend_met = not deficient if data_complete else None
    active = payload.get("account_active")
    unchanged = payload.get("product_unchanged")
    waived = payload.get("first_year_fee_waived")
    for label, value in (("account_active", active), ("product_unchanged", unchanged), ("first_year_fee_waived", waived)):
        if value is not None and not isinstance(value, bool):
            raise ValueError("%s must be true, false, or null" % label)

    is_first_year = cycle_start == opened
    disqualifiers = []
    if active is False:
        disqualifiers.append("account is closed")
    if unchanged is False:
        disqualifiers.append("account was product-changed")
    if is_first_year and waived is True:
        disqualifiers.append("first cardmember year had an annual-fee waiver")

    unknown_conditions = []
    if active is None:
        unknown_conditions.append("current account status")
    if unchanged is None:
        unknown_conditions.append("whether the account was product-changed before evaluation")
    if is_first_year and waived is None:
        unknown_conditions.append("whether the first-year annual fee was waived")

    if not data_complete:
        status = "insufficient_transaction_data"
    elif disqualifiers:
        status = "not_qualified"
    elif spend_met is False:
        status = "not_qualified"
    elif unknown_conditions:
        status = "conditional"
    else:
        status = "qualified"

    return {
        "ok": True,
        "data_complete": data_complete,
        "data_issues": issues,
        "account_open_date": opened.isoformat(),
        "as_of_date": as_of.isoformat(),
        "cardmember_year_start": cycle_start.isoformat(),
        "cardmember_year_end_exclusive": cycle_end.isoformat(),
        "cardmember_year_end_inclusive": (cycle_end.fromordinal(cycle_end.toordinal() - 1)).isoformat(),
        "threshold": money(threshold),
        "rebate_amount": money(rebate),
        "spend_requirement_met": spend_met,
        "qualification_status": status,
        "deficient_windows": deficient,
        "known_disqualifiers": disqualifiers,
        "unconfirmed_conditions": unknown_conditions,
        "windows": windows,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw), sort_keys=True))
    except (json.JSONDecodeError, KeyError, ValueError) as error:
        emit_error(str(error))
