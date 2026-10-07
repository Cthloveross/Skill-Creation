#!/usr/bin/env python3
"""Select and format a verified customer's credit-card transaction report.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
performs no authentication and has no banking-tool access.
"""

import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d")
MONEY_QUANTUM = Decimal("0.01")


def text(value):
    return "" if value is None else str(value)


def normalized(value):
    return " ".join(text(value).split()).casefold()


def parse_date(value):
    raw = text(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    raise ValueError("date must use MM/DD/YYYY or YYYY-MM-DD")


def parse_money(value):
    if isinstance(value, bool):
        raise ValueError("amount must not be boolean")
    raw = text(value).strip().replace(",", "")
    negative_parentheses = raw.startswith("(") and raw.endswith(")")
    if negative_parentheses:
        raw = "-" + raw[1:-1]
    raw = raw.replace("$", "").strip()
    try:
        return Decimal(raw).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise ValueError("amount is not a valid currency value")


def format_money(amount):
    sign = "-" if amount < 0 else ""
    return sign + "$" + format(abs(amount), ",.2f")


def main(payload):
    errors = []
    warnings = []
    for key in ("accounts", "requested_card_type", "transactions"):
        if key not in payload:
            errors.append("missing required field: " + key)

    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}
    if not isinstance(payload["accounts"], list) or not isinstance(payload["transactions"], list):
        return {"ok": False, "errors": ["accounts and transactions must be arrays"], "warnings": warnings}

    requested = normalized(payload["requested_card_type"])
    if not requested:
        return {"ok": False, "errors": ["requested_card_type must be nonempty"], "warnings": warnings}

    matches = [a for a in payload["accounts"] if isinstance(a, dict) and normalized(a.get("card_type")) == requested]
    if len(matches) != 1:
        return {
            "ok": False,
            "errors": ["requested card must match exactly one account; found %d matches" % len(matches)],
            "warnings": warnings,
        }
    account = matches[0]
    if not text(account.get("user_id")).strip():
        warnings.append("selected account has no user_id; caller must verify ownership before disclosure")

    try:
        limit = int(payload.get("limit", 10))
        if limit < 1 or limit > 100:
            raise ValueError
    except (TypeError, ValueError):
        return {"ok": False, "errors": ["limit must be an integer from 1 through 100"], "warnings": warnings}

    try:
        start = parse_date(payload["start_date"]) if payload.get("start_date") else None
        end = parse_date(payload["end_date"]) if payload.get("end_date") else None
        if start and end and start > end:
            raise ValueError("start_date must not be after end_date")
        minimum = parse_money(payload["min_amount"]) if payload.get("min_amount") is not None else None
        maximum = parse_money(payload["max_amount"]) if payload.get("max_amount") is not None else None
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("min_amount must not exceed max_amount")
    except ValueError as exc:
        return {"ok": False, "errors": [str(exc)], "warnings": warnings}

    merchant_filter = normalized(payload.get("merchant_contains"))
    posted_raw = payload.get("posted_statuses")
    if posted_raw is not None and (not isinstance(posted_raw, list) or not all(isinstance(x, str) for x in posted_raw)):
        return {"ok": False, "errors": ["posted_statuses must be an array of strings"], "warnings": warnings}
    posted_statuses = {normalized(item) for item in posted_raw or []}

    chosen = []
    malformed = 0
    for index, transaction in enumerate(payload["transactions"]):
        if not isinstance(transaction, dict):
            malformed += 1
            continue
        if normalized(transaction.get("credit_card_type")) != requested:
            continue
        try:
            date_value = parse_date(transaction.get("transaction_date"))
            amount = parse_money(transaction.get("transaction_amount"))
        except ValueError:
            malformed += 1
            continue
        merchant = text(transaction.get("merchant_name")).strip()
        if not merchant:
            malformed += 1
            continue
        status = text(transaction.get("status")).strip()
        if start and date_value < start or end and date_value > end:
            continue
        if merchant_filter and merchant_filter not in normalized(merchant):
            continue
        if minimum is not None and amount < minimum or maximum is not None and amount > maximum:
            continue
        if posted_raw is not None and normalized(status) not in posted_statuses:
            continue
        chosen.append((date_value, text(transaction.get("transaction_id")), index, transaction, amount, merchant, status))

    if malformed:
        warnings.append("%d matching transaction record(s) were skipped because date, amount, or merchant data was invalid" % malformed)
    if posted_raw is None:
        warnings.append("No posted-status mapping was supplied; statuses are displayed without inferring posting state")

    chosen.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    chosen = chosen[:limit]
    output_transactions = []
    total = Decimal("0.00")
    for date_value, _, _, transaction, amount, merchant, status in chosen:
        total += amount
        item = {
            "transaction_id": transaction.get("transaction_id"),
            "transaction_date": date_value.isoformat(),
            "merchant_name": merchant,
            "transaction_amount": format_money(amount),
            "category": transaction.get("category"),
            "status": status or None,
        }
        output_transactions.append(item)

    selected_account = {
        "account_id": account.get("account_id"),
        "user_id": account.get("user_id"),
        "card_type": account.get("card_type"),
        "current_balance": account.get("current_balance"),
    }
    return {
        "ok": True,
        "selected_account": selected_account,
        "filters": {
            "start_date": start.isoformat() if start else None,
            "end_date": end.isoformat() if end else None,
            "merchant_contains": payload.get("merchant_contains"),
            "min_amount": format_money(minimum) if minimum is not None else None,
            "max_amount": format_money(maximum) if maximum is not None else None,
            "posted_statuses": posted_raw,
            "limit": limit,
        },
        "transaction_count": len(output_transactions),
        "shown_total_amount": format_money(total),
        "transactions": output_transactions,
        "warnings": warnings,
    }


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("input must be a JSON object")
        result = main(incoming)
    except (json.JSONDecodeError, ValueError) as exc:
        result = {"ok": False, "errors": [str(exc)], "warnings": []}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
