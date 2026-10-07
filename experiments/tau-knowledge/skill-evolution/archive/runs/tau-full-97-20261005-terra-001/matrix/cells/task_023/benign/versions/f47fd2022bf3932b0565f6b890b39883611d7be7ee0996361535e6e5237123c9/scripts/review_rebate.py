#!/usr/bin/env python3
"""Calculate Platinum Rewards Card annual-fee rebate eligibility from JSON stdin."""
import calendar
import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
DEFAULT_THRESHOLD = Decimal("7500.00")
PROMO_START = date(2024, 6, 1)
PROMO_END = date(2024, 12, 31)
PURCHASE_KINDS = {"purchase", "virtual_purchase", "international_purchase"}
ADJUSTMENT_KINDS = {"return", "refund", "credit"}
EXCLUDED_KINDS = {
    "fee", "interest", "adjustment", "cash_advance", "cash_equivalent",
    "balance_transfer", "p2p_transfer", "funding_transaction", "disputed",
}


def parse_date(value, field):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD)")


def parse_money(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("amount is missing or invalid")
    text = str(value).strip().replace("$", "").replace(",", "")
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return Decimal(text).quantize(CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError("amount is invalid")


def money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def anniversary(anchor, months, resolution):
    month_number = anchor.month - 1 + months
    year = anchor.year + month_number // 12
    month = month_number % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    if anchor.day > last_day:
        if resolution == "strict":
            raise ValueError(
                "policy does not define this non-existent monthly anniversary; "
                "supply an authorized anniversary_day_resolution"
            )
        if resolution != "clamp":
            raise ValueError("anniversary_day_resolution must be strict or clamp")
        day = last_day
    else:
        day = anchor.day
    return date(year, month, day)


def anniversary_index(anchor, candidate, resolution):
    rough = (candidate.year - anchor.year) * 12 + candidate.month - anchor.month
    if rough < 0 or anniversary(anchor, rough, resolution) != candidate:
        raise ValueError("fee_billed_year_start must be an account anniversary date")
    return rough


def classify(transaction):
    """Return included, excluded, or unknown based on explicit supplied facts."""
    if transaction.get("counts_toward_threshold") is True:
        return "included"
    if transaction.get("counts_toward_threshold") is False:
        return "excluded"
    if transaction.get("is_disputed") and not transaction.get("dispute_resolved", False):
        return "excluded"
    kind = str(transaction.get("transaction_kind", "")).strip().lower()
    if kind in PURCHASE_KINDS or kind in ADJUSTMENT_KINDS:
        return "included"
    if kind in EXCLUDED_KINDS:
        return "excluded"
    return "unknown"


def transaction_id(transaction, fallback):
    return str(transaction.get("transaction_id", transaction.get("id", fallback)))


def select_year_start(data, opening, as_of, resolution):
    supplied = data.get("fee_billed_year_start")
    if supplied:
        start = parse_date(supplied, "fee_billed_year_start")
        index = anniversary_index(opening, start, resolution)
        if index % 12 != 0:
            raise ValueError("fee_billed_year_start must start a 12-window cardmember year")
        return start, "supplied_fee_billed_year_start"

    explicit_waiver = data.get("first_year_fee_waived")
    promo_applies = PROMO_START <= opening <= PROMO_END
    waived = promo_applies if explicit_waiver is None else bool(explicit_waiver)
    first_index = 12 if waived else 0
    selected = None
    index = first_index
    while True:
        start = anniversary(opening, index, resolution)
        end = anniversary(opening, index + 12, resolution) - timedelta(days=1)
        if as_of > end:
            selected = start
            index += 12
        else:
            break
    if selected is None:
        raise ValueError("no completed fee-billed cardmember year is available as of as_of_date")
    basis = "documented_promo_waiver" if waived and promo_applies else (
        "explicit_first_year_waiver" if waived else "no_documented_first_year_waiver"
    )
    return selected, basis


def review(data):
    opening = parse_date(data.get("account_open_date"), "account_open_date")
    as_of = parse_date(data.get("as_of_date"), "as_of_date")
    if as_of < opening:
        raise ValueError("as_of_date cannot precede account_open_date")
    resolution = data.get("anniversary_day_resolution", "strict")
    threshold = parse_money(data.get("threshold", DEFAULT_THRESHOLD))
    if threshold < 0:
        raise ValueError("threshold cannot be negative")
    start, basis = select_year_start(data, opening, as_of, resolution)
    start_index = anniversary_index(opening, start, resolution)
    windows = []
    for offset in range(12):
        window_start = anniversary(opening, start_index + offset, resolution)
        window_end = anniversary(opening, start_index + offset + 1, resolution) - timedelta(days=1)
        windows.append({
            "number": offset + 1, "start": window_start, "end": window_end,
            "total": Decimal("0.00"), "unknown": [], "included": [],
        })
    annual_end = windows[-1]["end"]
    if as_of <= annual_end:
        raise ValueError("selected cardmember year has not closed as of as_of_date")

    posted_statuses = {str(x).upper() for x in data.get("posted_statuses", ["POSTED", "COMPLETED"])}
    warnings = []
    for position, tx in enumerate(data.get("transactions", []), 1):
        txid = transaction_id(tx, f"transaction_{position}")
        status = str(tx.get("status", "")).upper()
        if status not in posted_statuses:
            continue
        try:
            posted = parse_date(tx.get("posting_date"), f"posting_date for {txid}")
        except ValueError as exc:
            warnings.append(str(exc))
            continue
        target = next((w for w in windows if w["start"] <= posted <= w["end"]), None)
        if target is None:
            continue
        classification = classify(tx)
        if classification == "excluded":
            continue
        if classification == "unknown":
            target["unknown"].append(txid)
            continue
        try:
            amount = parse_money(tx.get("amount"))
        except ValueError:
            target["unknown"].append(txid)
            warnings.append(f"amount is invalid for {txid}")
            continue
        target["total"] += amount
        target["included"].append(txid)

    missed = []
    indeterminate = False
    output_windows = []
    for window in windows:
        below = window["total"] < threshold
        if below and window["unknown"]:
            indeterminate = True
        elif below:
            missed.append(window["number"])
        output_windows.append({
            "number": window["number"], "start": window["start"].isoformat(),
            "end": window["end"].isoformat(),
            "net_qualifying_spend": money(window["total"]),
            "meets_threshold": not below,
            "unclassified_transaction_ids": window["unknown"],
            "included_transaction_ids": window["included"],
        })
    if indeterminate:
        spend_result = "indeterminate"
    elif missed:
        spend_result = "missed"
    else:
        spend_result = "met"

    fee_billed = data.get("annual_fee_billed")
    active = data.get("account_active_and_unchanged")
    if spend_result == "missed" or fee_billed is False or active is False:
        qualification = "not_eligible"
    elif spend_result == "indeterminate":
        qualification = "indeterminate"
    elif fee_billed is True and active is True:
        qualification = "eligible"
    else:
        qualification = "spend_requirement_met_pending_fee_or_account_status"

    return {
        "annual_year_start": start.isoformat(), "annual_year_end": annual_end.isoformat(),
        "as_of_date": as_of.isoformat(), "fee_year_selection_basis": basis,
        "window_count": 12, "monthly_threshold": money(threshold),
        "windows": output_windows, "missed_window_numbers": missed,
        "spend_requirement": spend_result, "annual_fee_billed": fee_billed,
        "account_active_and_unchanged": active, "qualification_status": qualification,
        "rebate_amount_if_qualified": "150.00", "warnings": warnings,
    }


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(review(data), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))


if __name__ == "__main__":
    main()
