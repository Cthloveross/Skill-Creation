#!/usr/bin/env python3
"""Build a safe, deterministic report for one credit-card transaction history.

Reads the JSON schema documented in SKILL.md from stdin and writes a JSON result.
Only Python's standard library is used.
"""

import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

POSTED_STATUSES = {"COMPLETED", "POSTED"}
DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y")


def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError("date is missing or not a string")
    text = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError("unsupported date format: %s" % value)


def parse_amount(value):
    if isinstance(value, bool):
        raise ValueError("amount must not be boolean")
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise ValueError("amount is missing or has an unsupported type")
    negative_parentheses = text.startswith("(") and text.endswith(")")
    if negative_parentheses:
        text = text[1:-1]
    text = text.replace("$", "").replace(",", "").strip()
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("unparseable amount: %r" % value) from exc
    if negative_parentheses:
        amount = -amount
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def money(amount):
    amount = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if amount < 0 else ""
    return sign + "${:,.2f}".format(abs(amount))


def fail(message):
    return {"ok": False, "error": message}


def nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def build(payload):
    if not isinstance(payload, dict):
        return fail("input must be a JSON object")
    accounts = payload.get("accounts")
    transactions = payload.get("transactions")
    card_type = payload.get("card_type")
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        return fail("accounts and transactions must both be arrays")
    if not nonempty_string(card_type):
        return fail("card_type is required")

    selected = [a for a in accounts if isinstance(a, dict) and a.get("card_type") == card_type]
    if not selected:
        return fail("no account matches the requested card type")
    if len(selected) != 1:
        return fail("multiple accounts match the requested card type; account selection is ambiguous")
    account = selected[0]

    try:
        start = parse_date(payload["start_date"]) if payload.get("start_date") else None
        end = parse_date(payload["end_date"]) if payload.get("end_date") else None
    except ValueError as exc:
        return fail(str(exc))
    if start and end and start > end:
        return fail("start_date must not be after end_date")

    limit = payload.get("recent_count")
    if limit is not None:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            return fail("recent_count must be a positive integer or null")

    posted_only = payload.get("posted_only", True)
    if not isinstance(posted_only, bool):
        return fail("posted_only must be boolean")

    included = []
    card_match_count = 0
    status_excluded_count = 0
    date_excluded_count = 0
    for index, txn in enumerate(transactions):
        if not isinstance(txn, dict) or txn.get("credit_card_type") != card_type:
            continue
        card_match_count += 1
        status = str(txn.get("status", "")).strip().upper()
        if posted_only and status not in POSTED_STATUSES:
            status_excluded_count += 1
            continue
        try:
            txn_date = parse_date(txn.get("transaction_date"))
            amount = parse_amount(txn.get("transaction_amount"))
        except ValueError as exc:
            return fail("matching transaction %d is invalid: %s" % (index, exc))
        merchant = txn.get("merchant_name")
        if not nonempty_string(merchant):
            return fail("matching transaction %d has no merchant descriptor" % index)
        if (start and txn_date < start) or (end and txn_date > end):
            date_excluded_count += 1
            continue
        included.append({
            "transaction_id": txn.get("transaction_id"),
            "date": txn_date.isoformat(),
            "merchant": merchant.strip(),
            "amount": money(amount),
            "amount_decimal": str(amount),
            "category": txn.get("category"),
            "status": txn.get("status"),
            "_date": txn_date,
            "_amount": amount,
        })

    included.sort(key=lambda row: (row["_date"], str(row.get("transaction_id") or "")), reverse=True)
    matching_after_filters = len(included)
    if limit is not None:
        included = included[:limit]
    total = sum((row["_amount"] for row in included), Decimal("0.00"))
    for row in included:
        row.pop("_date")
        row.pop("_amount")
        row.pop("amount_decimal")

    result_account = {
        "account_id": account.get("account_id"),
        "card_type": account.get("card_type"),
    }
    if account.get("current_balance") is not None:
        try:
            result_account["current_balance"] = money(parse_amount(account["current_balance"]))
        except ValueError as exc:
            return fail("selected account has invalid current_balance: %s" % exc)

    return {
        "ok": True,
        "account": result_account,
        "transactions": included,
        "displayed_count": len(included),
        "matching_after_date_and_status_filters": matching_after_filters,
        "matching_card_transaction_count": card_match_count,
        "excluded_for_nonposted_status": status_excluded_count,
        "excluded_for_date_range": date_excluded_count,
        "displayed_net_total": money(total),
        "total_label": "Net total of displayed posted transactions" if posted_only else "Net total of displayed transactions",
        "note": "This total covers only displayed rows and is not a reconciliation of the current balance.",
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps(fail("invalid JSON input: %s" % exc.msg)))
        return
    try:
        result = build(payload)
    except Exception as exc:  # Keep the command interface structured for unexpected malformed inputs.
        result = fail("unable to build report: %s" % exc)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
