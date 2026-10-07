#!/usr/bin/env python3
"""Evaluate annual-fee rebate eligibility from normalized posted transactions.

Read one JSON object on stdin; write one JSON object on stdout. See SKILL.md for
schema and interpretation. This utility does not access banking systems or take
any account action.
"""
import calendar
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MONEY = Decimal("0.01")
EXCLUDED_WORDS = (
    "fee", "interest", "adjustment", "balance transfer", "cash advance",
    "cash equivalent", "cash-equivalent", "money order", "traveler",
    "p2p", "person to person", "person-to-person", "funding",
)
DISPUTED_WORDS = ("disputed", "unresolved dispute", "pending dispute")

def money(value):
    if isinstance(value, str):
        value = value.replace("$", "").replace(",", "").strip()
        if value.startswith("(") and value.endswith(")"):
            value = "-" + value[1:-1]
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)

def money_text(value):
    return format(value.quantize(MONEY, rounding=ROUND_HALF_UP), ".2f")

def parse_date(value, field):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError("%s must be YYYY-MM-DD" % field)

def add_months_same_day(start, months):
    """Advance a date retaining its day; reject unspecified short-month cases."""
    target = (start.year * 12 + start.month - 1) + months
    year, month0 = divmod(target, 12)
    month = month0 + 1
    if start.day > calendar.monthrange(year, month)[1]:
        raise ValueError(
            "Policy does not specify monthly-anniversary handling for day %d in %04d-%02d"
            % (start.day, year, month)
        )
    return date(year, month, start.day)

def normal_status(tx):
    return str(tx.get("status", "")).strip().lower()

def classify(tx):
    """Return (eligible-or-None, reason). None means cannot safely classify."""
    if "is_eligible" in tx:
        value = tx["is_eligible"]
        if isinstance(value, bool):
            return value, "explicit is_eligible"
        return None, "is_eligible is not boolean"
    status = normal_status(tx)
    if status not in ("completed", "posted"):
        if any(x in status for x in DISPUTED_WORDS):
            return False, "unresolved/disputed status"
        return None, "status is not clearly posted/completed"
    labels = " ".join(str(tx.get(k, "")) for k in ("category", "type", "transaction_type", "description")).lower()
    if any(x in labels for x in DISPUTED_WORDS):
        return False, "unresolved/disputed transaction"
    if any(x in labels for x in EXCLUDED_WORDS):
        return False, "excluded transaction type"
    # A completed positive or negative purchase-like record is countable. A source
    # with no category/type is not assumed to be a purchase.
    if not labels.strip():
        return None, "missing transaction classification; provide is_eligible"
    return True, "completed purchase-like transaction"

def choose_start(opened, as_of, waived, override):
    start0 = parse_date(override, "cardmember_year_start") if override else opened
    if waived and not override:
        start0 = add_months_same_day(opened, 12)
    # Find the latest annual period which has fully closed. End is exclusive.
    current = start0
    latest = None
    while True:
        end = add_months_same_day(current, 12)
        if end <= as_of:
            latest = current
            current = end
        else:
            return latest

def insufficient(reason, warnings=None):
    output = {"status": "insufficient_information", "reason": reason}
    if warnings:
        output["warnings"] = warnings
    return output

def main(payload):
    try:
        opened = parse_date(payload["account_open_date"], "account_open_date")
        as_of = parse_date(payload["as_of_date"], "as_of_date")
        threshold = money(payload.get("threshold", "7500.00"))
        if threshold < 0:
            return insufficient("threshold must not be negative")
    except KeyError as exc:
        return insufficient("missing required field: %s" % exc.args[0])
    except (ValueError, InvalidOperation) as exc:
        return insufficient(str(exc))

    if opened.day > 28:
        return insufficient("monthly anniversary rule is unspecified for account-opening day after the 28th")
    if as_of < opened:
        return insufficient("as_of_date is before account opening")
    if not payload.get("transactions_card_attributable", True):
        return insufficient("transactions cannot be attributed reliably to the selected card")
    if not payload.get("history_complete", True):
        return insufficient("transaction history is marked incomplete")

    try:
        start = choose_start(opened, as_of, bool(payload.get("first_year_fee_waived", False)), payload.get("cardmember_year_start"))
    except ValueError as exc:
        return insufficient(str(exc))
    if start is None:
        return insufficient("no fully completed applicable 12-window cardmember year as of the review date")

    try:
        boundaries = [add_months_same_day(start, i) for i in range(13)]
    except ValueError as exc:
        return insufficient(str(exc))
    totals = [Decimal("0.00") for _ in range(12)]
    warnings = []
    included = [0 for _ in range(12)]
    for idx, tx in enumerate(payload.get("transactions", [])):
        try:
            posted = parse_date(tx.get("posted_date", tx.get("transaction_date")), "transactions[%d].posted_date" % idx)
            amount = money(tx["amount"])
        except (ValueError, InvalidOperation, KeyError) as exc:
            return insufficient("invalid transaction at index %d: %s" % (idx, exc))
        eligible, reason = classify(tx)
        if eligible is None and boundaries[0] <= posted < boundaries[-1]:
            warnings.append("transaction index %d cannot be safely classified: %s" % (idx, reason))
            continue
        if not eligible or not (boundaries[0] <= posted < boundaries[-1]):
            continue
        for window in range(12):
            if boundaries[window] <= posted < boundaries[window + 1]:
                totals[window] += amount
                included[window] += 1
                break
    if warnings:
        return insufficient("one or more in-period transactions have unknown eligibility", warnings)

    windows = []
    for i, total in enumerate(totals):
        shortfall = max(Decimal("0.00"), threshold - total)
        windows.append({
            "window_number": i + 1,
            "start": boundaries[i].isoformat(),
            "end_exclusive": boundaries[i + 1].isoformat(),
            "net_qualifying_spend": money_text(total),
            "threshold": money_text(threshold),
            "meets_threshold": total >= threshold,
            "shortfall": money_text(shortfall),
            "included_transaction_count": included[i],
        })
    all_months = all(row["meets_threshold"] for row in windows)
    active = bool(payload.get("account_active", True))
    result = {
        "status": "eligible" if all_months and active else "not_eligible",
        "evaluation_start": boundaries[0].isoformat(),
        "evaluation_end_exclusive": boundaries[-1].isoformat(),
        "threshold": money_text(threshold),
        "all_12_months_met_threshold": all_months,
        "account_active": active,
        "windows": windows,
    }
    if not all_months:
        result["failure_reason"] = "At least one monthly anniversary window did not meet the threshold."
        result["failed_windows"] = [w["window_number"] for w in windows if not w["meets_threshold"]]
    elif not active:
        result["failure_reason"] = "Account is closed or product-changed before evaluation/posting."
    return result

if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"status": "insufficient_information", "reason": "invalid evaluator input: %s" % exc}, separators=(",", ":")))
