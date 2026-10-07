#!/usr/bin/env python3
"""Calculate a Platinum Rewards annual-fee rebate review from JSON stdin.

The program uses only the Python standard library.  See SKILL.md for schema.
"""
import calendar
import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

EXCLUDED_WORDS = (
    "fee", "interest", "adjustment", "cash advance", "cash-equivalent",
    "cash equivalent", "balance transfer", "person-to-person", "p2p", "funding",
)
EXCLUDED_KINDS = {
    "fee", "interest", "adjustment", "cash_advance", "cash_equivalent",
    "balance_transfer", "p2p_transfer", "person_to_person", "funding",
}
VALID_POSTED_STATUSES = {"COMPLETED", "POSTED", "SETTLED"}
MONEY = Decimal("0.01")


def money(value):
    """Parse an amount, including ordinary display strings, to exact cents."""
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        raise ValueError("transaction amount must be a number or string")
    cleaned = value.strip().replace("$", "").replace(",", "")
    try:
        return Decimal(cleaned).quantize(MONEY, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError("invalid currency amount: %r" % value) from exc


def parse_date(value, label):
    if not isinstance(value, str):
        raise ValueError(label + " must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(label + " must be YYYY-MM-DD") from exc


def add_months_same_day(value, months):
    """Advance an anniversary without silently choosing an end-of-month rule."""
    if value.day > 28:
        raise ValueError(
            "opening/evaluation anniversary after the 28th is unsupported: "
            "the supplied policy does not define absent-calendar-day handling"
        )
    index = value.year * 12 + (value.month - 1) + months
    return date(index // 12, index % 12 + 1, value.day)


def field(record, key):
    value = record.get(key)
    return value.strip() if isinstance(value, str) else value


def parse_history_text(text):
    """Parse the stable, human-readable credit-card transaction tool result."""
    if not isinstance(text, str):
        raise ValueError("transactions_text must be a string")
    chunks = re.findall(
        r"(?ms)^\s*\d+\.\s+Record ID:.*?(?=^\s*\d+\.\s+Record ID:|\Z)", text
    )
    records = []
    labels = {
        "credit_card_type": "credit_card_type",
        "transaction_amount": "amount",
        "transaction_date": "posting_date",
        "category": "category",
        "status": "status",
        "transaction_id": "transaction_id",
    }
    for chunk in chunks:
        record = {}
        for source, destination in labels.items():
            match = re.search(r"(?m)^\s*" + re.escape(source) + r":\s*(.*?)\s*$", chunk)
            if match:
                record[destination] = match.group(1)
        if record:
            records.append(record)
    if not records:
        raise ValueError("no transaction records could be parsed from transactions_text")
    return records


def is_excluded(record):
    kind = str(field(record, "transaction_kind") or "").lower().replace("-", "_").replace(" ", "_")
    if kind in EXCLUDED_KINDS or kind in {"refund", "return", "credit"}:
        # Refunds/credits with negative amounts must still reduce spend. A positive
        # adjustment is excluded, while a negative one is retained below.
        if kind in {"refund", "return", "credit"}:
            return False
        return True
    descriptor = " ".join(str(field(record, x) or "") for x in ("category", "description", "merchant_name")).lower()
    return any(word in descriptor for word in EXCLUDED_WORDS)


def normalize_records(raw_records, target_card_type):
    included, excluded = [], []
    for position, record in enumerate(raw_records, start=1):
        if not isinstance(record, dict):
            raise ValueError("transaction %d is not an object" % position)
        card_type = field(record, "credit_card_type")
        if target_card_type and card_type and card_type != target_card_type:
            continue
        if target_card_type and not card_type:
            raise ValueError("transaction %d lacks credit_card_type for account filtering" % position)
        posted = field(record, "posting_date") or field(record, "transaction_date")
        txn_date = parse_date(posted, "transaction %d posting_date" % position)
        amount = money(field(record, "amount") if field(record, "amount") is not None else field(record, "transaction_amount"))
        status = str(field(record, "status") or "").upper()
        identifier = field(record, "transaction_id") or "record_%d" % position
        if status not in VALID_POSTED_STATUSES:
            excluded.append({"transaction_id": identifier, "reason": "not a completed/posted transaction"})
            continue
        if "DISPUT" in status:
            excluded.append({"transaction_id": identifier, "reason": "unresolved dispute"})
            continue
        if is_excluded(record):
            excluded.append({"transaction_id": identifier, "reason": "excluded transaction type/category"})
            continue
        included.append({"transaction_id": identifier, "posting_date": txn_date, "amount": amount})
    return included, excluded


def choose_year_start(opened, as_of, requested):
    if requested:
        start = parse_date(requested, "evaluation_start")
        if start.day != opened.day:
            raise ValueError("evaluation_start must use the account opening anniversary day")
        if add_months_same_day(start, 12) > as_of:
            raise ValueError("requested cardmember year is not complete as of as_of_date")
        return start
    start = opened
    while add_months_same_day(start, 12) <= as_of:
        start = add_months_same_day(start, 12)
    if start == opened:
        raise ValueError("no completed 12-window cardmember year exists as of as_of_date")
    return add_months_same_day(start, -12)


def analysis(payload):
    opened = parse_date(payload.get("account_open_date"), "account_open_date")
    as_of = parse_date(payload.get("as_of_date"), "as_of_date")
    if as_of < opened:
        raise ValueError("as_of_date is before account_open_date")
    threshold = money(payload.get("monthly_threshold", "7500.00"))
    rebate = money(payload.get("rebate_amount", "150.00"))
    if threshold < 0 or rebate < 0:
        raise ValueError("threshold and rebate_amount must be non-negative")
    year_start = choose_year_start(opened, as_of, payload.get("evaluation_start"))
    year_end = add_months_same_day(year_start, 12)

    if "transactions" in payload:
        raw = payload["transactions"]
        if not isinstance(raw, list):
            raise ValueError("transactions must be an array")
    elif "transactions_text" in payload:
        raw = parse_history_text(payload["transactions_text"])
    else:
        raise ValueError("provide transactions or transactions_text")

    included, excluded = normalize_records(raw, payload.get("target_card_type"))
    windows = []
    for index in range(12):
        start = add_months_same_day(year_start, index)
        end_exclusive = add_months_same_day(year_start, index + 1)
        window_txns = [t for t in included if start <= t["posting_date"] < end_exclusive]
        total = sum((t["amount"] for t in window_txns), Decimal("0.00")).quantize(MONEY)
        windows.append({
            "window_number": index + 1,
            "start": start.isoformat(),
            "end_inclusive": (end_exclusive.fromordinal(end_exclusive.toordinal() - 1)).isoformat(),
            "net_eligible_posted_spend": format(total, ".2f"),
            "transaction_count": len(window_txns),
            "meets_threshold": total >= threshold,
        })
    failed = [w for w in windows if not w["meets_threshold"]]
    spend_met = not failed
    fee_billed = payload.get("fee_billed")
    open_unchanged = payload.get("account_open_and_unchanged")
    if not spend_met:
        decision = "not_eligible_spend"
    elif fee_billed is False:
        decision = "not_applicable_fee_waived"
    elif fee_billed is True and open_unchanged is True:
        decision = "eligible"
    else:
        decision = "spend_qualified_pending_account_conditions"
    return {
        "evaluation_year_start": year_start.isoformat(),
        "evaluation_year_end_inclusive": (year_end.fromordinal(year_end.toordinal() - 1)).isoformat(),
        "monthly_threshold": format(threshold, ".2f"),
        "rebate_amount": format(rebate, ".2f"),
        "monthly_windows": windows,
        "failed_windows": failed,
        "spend_requirement_met": spend_met,
        "excluded_transaction_count": len(excluded),
        "excluded_transactions": excluded,
        "fee_billed": fee_billed if isinstance(fee_billed, bool) else None,
        "account_open_and_unchanged": open_unchanged if isinstance(open_unchanged, bool) else None,
        "decision": decision,
        "posting_note": "A qualified rebate is applied after the annual fee is billed; this calculation does not verify that a statement credit has posted.",
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps({"ok": True, "report": analysis(payload)}, indent=2, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))


if __name__ == "__main__":
    main()
