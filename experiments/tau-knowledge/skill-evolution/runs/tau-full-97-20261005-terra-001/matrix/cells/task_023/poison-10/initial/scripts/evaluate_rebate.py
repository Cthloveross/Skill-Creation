#!/usr/bin/env python3
"""Deterministically assess an anniversary-window annual-fee rebate.

Reads the JSON schema documented in SKILL.md from stdin and writes one JSON
object to stdout. Uses only the Python standard library.
"""
import calendar
import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MONEY = Decimal("0.01")
DEFAULT_THRESHOLD = Decimal("7500.00")
DEFAULT_REBATE = Decimal("150.00")
POSTED_STATUSES = {"COMPLETED", "POSTED"}
EXCLUDED_TYPES = {
    "fee", "fees", "interest", "cash_advance", "cash_equivalent",
    "balance_transfer", "p2p_transfer", "funding", "adjustment",
    "dispute", "unresolved_dispute",
}
REDUCTION_TYPES = {"refund", "return", "credit"}


def money(value):
    try:
        return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("amount must be a decimal number")


def parse_day(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field} must be a valid YYYY-MM-DD date")


def add_months_same_day(start, months):
    """Add months only where the same calendar day exists.

    The governing policy does not provide a fallback convention for dates such
    as the 29th through 31st in shorter months, so this deliberately errors.
    """
    index = (start.month - 1) + months
    year = start.year + index // 12
    month = index % 12 + 1
    if start.day > calendar.monthrange(year, month)[1]:
        raise ValueError(
            "unsupported anniversary calendar edge case: policy does not define "
            f"a {start.day}th-day anniversary in {year:04d}-{month:02d}"
        )
    return date(year, month, start.day)


def previous_anniversary_before(opened, as_of):
    """Return the latest anniversary strictly before the as-of date."""
    months = (as_of.year - opened.year) * 12 + as_of.month - opened.month
    while months >= 0:
        try:
            candidate = add_months_same_day(opened, months)
        except ValueError:
            raise
        if candidate < as_of:
            return candidate
        months -= 1
    raise ValueError("as_of precedes the account opening date")


def bool_or_gap(obj, key, gaps, label=None):
    value = obj.get(key)
    if not isinstance(value, bool):
        gaps.append(label or f"missing or non-boolean {key}")
        return None
    return value


def transaction_effect(tx, account_id, card_type):
    """Return (effect, reason, warning); effect is Decimal or None.

    An explicit counts_toward_threshold classification is authoritative but a
    completed posted date and account/card match are still required upstream.
    """
    status = str(tx.get("status", "")).upper()
    if status not in POSTED_STATUSES:
        return None, "not posted/completed", None
    if tx.get("account_id") not in (None, account_id):
        return None, "different account", None
    if tx.get("account_id") is None and tx.get("card_type") not in (None, card_type):
        return None, "different card type", None
    try:
        amount = money(tx.get("amount"))
    except ValueError:
        return None, "invalid amount", "transaction has an invalid amount"

    explicit = tx.get("counts_toward_threshold")
    kind = str(tx.get("transaction_type", "purchase")).strip().lower()
    if explicit is False:
        return None, "explicitly ineligible", None
    if kind in EXCLUDED_TYPES:
        return None, f"excluded type: {kind}", None
    if explicit is not True and kind not in REDUCTION_TYPES and kind != "purchase":
        return None, f"unclassified type: {kind}", "transaction type requires review"
    if kind in REDUCTION_TYPES:
        return -abs(amount), "included reduction", None
    return amount, "included purchase", None


def evaluate(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    account = payload.get("account")
    if not isinstance(account, dict):
        raise ValueError("account object is required")
    if account.get("card_type") != "Platinum Rewards Card":
        raise ValueError("this Skill supports only Platinum Rewards Card")
    account_id = account.get("account_id")
    if not isinstance(account_id, str) or not account_id:
        raise ValueError("account.account_id is required")
    opened = parse_day(account.get("opened_on"), "account.opened_on")
    as_of = parse_day(payload.get("as_of"), "as_of")
    threshold = money(payload.get("threshold", DEFAULT_THRESHOLD))
    rebate = money(payload.get("rebate_amount", DEFAULT_REBATE))
    if threshold < 0 or rebate < 0:
        raise ValueError("threshold and rebate_amount cannot be negative")

    if payload.get("evaluation_start") is not None:
        start = parse_day(payload["evaluation_start"], "evaluation_start")
        # Verify it is a supported anniversary of opening.
        delta = (start.year - opened.year) * 12 + start.month - opened.month
        if delta < 0 or add_months_same_day(opened, delta) != start:
            raise ValueError("evaluation_start must be an account-opening anniversary")
    else:
        last_start = previous_anniversary_before(opened, as_of)
        start = add_months_same_day(last_start, -12)

    windows = []
    for n in range(12):
        window_start = add_months_same_day(start, n)
        next_start = add_months_same_day(start, n + 1)
        windows.append({
            "number": n + 1,
            "start": window_start,
            "end": next_start - timedelta(days=1),
            "total": Decimal("0.00"),
            "included_transaction_ids": [],
            "excluded_transactions": [],
            "warnings": [],
        })
    end = windows[-1]["end"]

    seen_ids = set()
    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        raise ValueError("transactions must be an array")
    for position, tx in enumerate(transactions):
        if not isinstance(tx, dict):
            raise ValueError("each transaction must be an object")
        txid = str(tx.get("transaction_id") or f"position-{position}")
        if txid in seen_ids:
            raise ValueError(f"duplicate transaction_id: {txid}")
        seen_ids.add(txid)
        posted = parse_day(tx.get("posted_on"), f"transactions[{position}].posted_on")
        target = next((w for w in windows if w["start"] <= posted <= w["end"]), None)
        if target is None:
            continue
        effect, reason, warning = transaction_effect(tx, account_id, account["card_type"])
        if effect is None:
            target["excluded_transactions"].append({"transaction_id": txid, "reason": reason})
        else:
            target["total"] += effect
            target["included_transaction_ids"].append(txid)
        if warning and warning not in target["warnings"]:
            target["warnings"].append(warning)

    for window in windows:
        window["total"] = window["total"].quantize(MONEY)
        window["meets_threshold"] = window["total"] >= threshold
        window["shortfall"] = max(Decimal("0.00"), threshold - window["total"]).quantize(MONEY)
        window["start"] = window["start"].isoformat()
        window["end"] = window["end"].isoformat()
        window["posted_eligible_net"] = format(window.pop("total"), ".2f")
        window["shortfall"] = format(window["shortfall"], ".2f")

    gaps = []
    if not bool_or_gap(payload, "transaction_history_complete", gaps):
        pass
    if not bool_or_gap(payload, "posting_dates_confirmed", gaps):
        pass
    if not bool_or_gap(payload, "transaction_scope_confirmed", gaps):
        pass
    fee_billed = bool_or_gap(account, "annual_fee_billed", gaps, "annual fee billing status is unavailable")
    fee_waived = bool_or_gap(account, "first_year_fee_waived", gaps, "fee-waiver status is unavailable")
    active = bool_or_gap(account, "account_active", gaps, "account active/closure status is unavailable")
    changed = bool_or_gap(account, "product_changed_before_evaluation", gaps, "product-change status is unavailable")
    for window in windows:
        if window["warnings"]:
            gaps.append(f"window {window['number']} contains transactions requiring classification review")

    failed = [w for w in windows if not w["meets_threshold"]]
    reasons = []
    if end >= as_of:
        status = "pending"
        reasons.append("the 12th monthly window has not closed before the as-of date")
    elif gaps:
        status = "insufficient_data"
        reasons.append("official eligibility cannot be confirmed until all data gaps are resolved")
    elif fee_waived:
        status = "not_eligible"
        reasons.append("the selected year has a waived annual fee, so no rebate applies")
    elif not fee_billed:
        status = "not_eligible"
        reasons.append("the selected year is not confirmed as a fee-billed cardmember year")
    elif not active or changed:
        status = "not_eligible"
        reasons.append("the account was closed or product-changed before evaluation/rebate posting")
    elif failed:
        status = "not_eligible"
        reasons.append("at least one monthly window is below the required threshold")
    else:
        status = "eligible"
        reasons.append("all 12 completed monthly windows meet the threshold")

    return {
        "status": status,
        "threshold": format(threshold, ".2f"),
        "rebate_amount_if_eligible": format(rebate, ".2f"),
        "rebate_amount_current_decision": format(rebate if status == "eligible" else Decimal("0.00"), ".2f"),
        "evaluation": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "as_of": as_of.isoformat(),
            "window_count": 12,
            "closed_before_as_of": end < as_of,
        },
        "all_months_met": not failed,
        "failed_window_count": len(failed),
        "failed_windows": [w["number"] for w in failed],
        "windows": windows,
        "data_gaps": list(dict.fromkeys(gaps)),
        "decision_reasons": reasons,
        "next_step": (
            "Do not initiate a credit; a qualifying rebate is applied as a statement credit after the annual fee is billed."
            if status == "eligible" else
            "Resolve the listed condition or data gap before making an official rebate determination."
        ),
    }


def main():
    try:
        result = evaluate(json.load(sys.stdin))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        result = {"status": "error", "error": str(exc)}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
