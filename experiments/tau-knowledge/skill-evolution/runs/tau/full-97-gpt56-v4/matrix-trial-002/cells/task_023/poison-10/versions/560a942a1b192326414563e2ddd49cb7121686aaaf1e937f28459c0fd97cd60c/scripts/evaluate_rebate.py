#!/usr/bin/env python3
"""Evaluate Platinum Rewards monthly-anniversary spend from JSON stdin.

Input and output schemas are documented in SKILL.md. This program is read-only:
it neither calls banking tools nor applies a rebate.
"""
import calendar
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
DEFAULT_THRESHOLD = Decimal("7500.00")
DEFAULT_REBATE = Decimal("150.00")
EXCLUDED_WORDS = {
    "fee", "fees", "interest", "cash advance", "cash-equivalent",
    "cash equivalent", "balance transfer", "money order", "traveler",
    "p2p", "person-to-person", "funding",
}
PURCHASE_WORDS = {"purchase", "purchases", "pos", "point-of-sale", "online purchase"}
POSTED_STATUSES = {"COMPLETED", "POSTED", "SETTLED"}
UNRESOLVED_WORDS = {"DISPUTED", "PENDING_DISPUTE", "UNRESOLVED"}


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a date string")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"{field} must be YYYY-MM-DD or MM/DD/YYYY")


def parse_money(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a monetary number or string")
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip().replace("$", "").replace(",", "")
    else:
        raise ValueError(f"{field} must be a monetary number or string")
    try:
        return Decimal(text).quantize(CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError(f"{field} is not a valid amount")


def anniversary(year, month, anchor_day):
    """Return exact anniversary or None if calendar date does not exist."""
    if anchor_day > calendar.monthrange(year, month)[1]:
        return None
    return date(year, month, anchor_day)


def add_months_exact(start, months, anchor_day):
    absolute = start.year * 12 + (start.month - 1) + months
    year, zero_month = divmod(absolute, 12)
    return anniversary(year, zero_month + 1, anchor_day)


def normalized_text(tx):
    return " ".join(str(tx.get(k, "")).lower() for k in ("transaction_type", "category", "coding", "description"))


def classify(tx):
    """Return (count, reason). Explicit eligibility takes precedence."""
    if "eligible" in tx:
        if tx["eligible"] is True:
            return True, "explicitly eligible"
        if tx["eligible"] is False:
            return False, "explicitly ineligible"
        return False, "eligible must be boolean when supplied"
    status = str(tx.get("status", "")).upper().strip()
    if status in UNRESOLVED_WORDS or "DISPUT" in status:
        return False, "unresolved dispute"
    if status and status not in POSTED_STATUSES:
        return False, f"not a posted/completed status ({status})"
    text = normalized_text(tx)
    if any(word in text for word in EXCLUDED_WORDS):
        return False, "excluded transaction coding/category"
    # Known ordinary retail categories in transaction histories are purchase-like.
    ordinary_categories = {
        "groceries", "dining", "shopping", "entertainment", "utilities",
        "travel", "retail", "health", "merchandise",
    }
    category = str(tx.get("category", "")).lower().strip()
    tx_type = str(tx.get("transaction_type", "")).lower().strip()
    if category in ordinary_categories or tx_type in PURCHASE_WORDS or any(w in text for w in PURCHASE_WORDS):
        return True, "purchase-like posted transaction"
    return False, "ambiguous transaction coding; explicit eligibility needed"


def tx_posting_date(tx, allow_transaction_date):
    if "posting_date" in tx:
        return parse_date(tx["posting_date"], "transactions[].posting_date")
    if allow_transaction_date and "transaction_date" in tx:
        return parse_date(tx["transaction_date"], "transactions[].transaction_date")
    raise ValueError("transaction lacks posting_date; transaction_date requires transaction_date_is_posting_date=true")


def select_completed_year(opened, as_of, waived):
    """Select the latest anniversary year ending strictly before/as of review date."""
    anchor = opened.day
    candidates = []
    for year in range(opened.year, as_of.year + 1):
        start = anniversary(year, opened.month, anchor)
        end_boundary = anniversary(year + 1, opened.month, anchor)
        if start is None or end_boundary is None:
            return None, "The account anniversary day does not exist in a needed year."
        if start < opened:
            continue
        if end_boundary <= as_of:
            index = year - opened.year
            if not (waived and index == 0):
                candidates.append((start, end_boundary, index))
    if not candidates:
        return None, "No completed non-waived 12-month cardmember year is available as of the review date."
    return candidates[-1], None


def evaluate(data):
    if not isinstance(data, dict):
        raise ValueError("stdin JSON must be an object")
    opened = parse_date(data.get("account_open_date"), "account_open_date")
    as_of = parse_date(data.get("as_of_date"), "as_of_date")
    if as_of < opened:
        raise ValueError("as_of_date cannot precede account_open_date")
    transactions = data.get("transactions")
    if not isinstance(transactions, list):
        raise ValueError("transactions must be an array")
    threshold = parse_money(data.get("threshold", DEFAULT_THRESHOLD), "threshold")
    rebate = parse_money(data.get("rebate_amount", DEFAULT_REBATE), "rebate_amount")
    if threshold < 0 or rebate < 0:
        raise ValueError("threshold and rebate_amount cannot be negative")
    waived = data.get("first_year_waived", False)
    if not isinstance(waived, bool):
        raise ValueError("first_year_waived must be boolean")

    chosen, problem = select_completed_year(opened, as_of, waived)
    if problem:
        return {"status": "unsupported" if "anniversary" in problem else "needs_information", "message": problem}
    start, end_boundary, year_index = chosen
    windows = []
    for i in range(12):
        ws = add_months_exact(start, i, opened.day)
        we_boundary = add_months_exact(start, i + 1, opened.day)
        if ws is None or we_boundary is None:
            return {"status": "unsupported", "message": "A required monthly anniversary date does not exist; no clamping rule was supplied."}
        windows.append({"start": ws, "end_boundary": we_boundary, "total": Decimal("0.00"), "transaction_ids": []})

    allowed_date_fallback = data.get("transaction_date_is_posting_date", False)
    if not isinstance(allowed_date_fallback, bool):
        raise ValueError("transaction_date_is_posting_date must be boolean")
    desired_card = data.get("card_type")
    excluded = []
    counted_ids = set()
    for pos, tx in enumerate(transactions):
        if not isinstance(tx, dict):
            raise ValueError("each transactions item must be an object")
        if desired_card and (tx.get("credit_card_type") or tx.get("card_type")) not in (None, desired_card):
            continue
        posted = tx_posting_date(tx, allowed_date_fallback)
        count, reason = classify(tx)
        ident = str(tx.get("transaction_id", tx.get("id", pos)))
        if not count:
            excluded.append({"transaction_id": ident, "posting_date": posted.isoformat(), "reason": reason})
            continue
        if not (start <= posted < end_boundary):
            continue
        amount = parse_money(tx.get("transaction_amount", tx.get("amount")), "transactions[].amount")
        for window in windows:
            if window["start"] <= posted < window["end_boundary"]:
                if ident in counted_ids:
                    raise ValueError(f"duplicate transaction identifier among counted entries: {ident}")
                counted_ids.add(ident)
                window["total"] += amount
                window["transaction_ids"].append(ident)
                break

    result_windows = []
    qualifying = True
    for window in windows:
        total = window["total"].quantize(CENT)
        meets = total >= threshold
        qualifying = qualifying and meets
        result_windows.append({
            "start_date": window["start"].isoformat(),
            "end_date": (window["end_boundary"].fromordinal(window["end_boundary"].toordinal() - 1)).isoformat(),
            "net_eligible_posted_total": f"{total:.2f}",
            "threshold": f"{threshold:.2f}",
            "meets_threshold": meets,
            "shortfall": f"{max(Decimal('0.00'), threshold - total):.2f}",
            "counted_transaction_ids": window["transaction_ids"],
        })

    account_active = data.get("account_active")
    changed = data.get("product_changed_before_evaluation")
    if account_active is False or changed is True:
        final = "not_eligible_account_status"
    elif qualifying:
        final = "qualified"
    else:
        final = "not_qualified"
    return {
        "status": "ok",
        "selected_cardmember_year_start": start.isoformat(),
        "selected_cardmember_year_end": (end_boundary.fromordinal(end_boundary.toordinal() - 1)).isoformat(),
        "year_number_since_opening": year_index + 1,
        "spend_qualification": final,
        "rebate_amount_if_qualified": f"{rebate:.2f}",
        "monthly_windows": result_windows,
        "excluded_or_ambiguous_transactions": excluded,
        "conditions_not_verified": [
            item for item, known in (
                ("account active through evaluation and rebate posting", account_active),
                ("no product change before evaluation or rebate posting", None if changed is None else not changed),
            ) if known is None
        ],
    }


def main():
    try:
        data = json.load(sys.stdin)
        print(json.dumps(evaluate(data), separators=(",", ":"), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, separators=(",", ":")))
        sys.exit(2)


if __name__ == "__main__":
    main()
