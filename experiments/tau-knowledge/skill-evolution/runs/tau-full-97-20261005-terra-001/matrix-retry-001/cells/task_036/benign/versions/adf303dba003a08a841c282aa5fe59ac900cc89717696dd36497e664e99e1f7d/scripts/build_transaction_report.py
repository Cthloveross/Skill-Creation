#!/usr/bin/env python3
"""Create a deterministic, read-only credit-card transaction report.

Reads one JSON object from stdin and writes one JSON object to stdout. See SKILL.md
for the input schema. This script uses only the Python standard library.
"""

import json
import sys
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MONEY = Decimal("0.01")


def fail(error, message):
    return {"ok": False, "error": error, "message": message}


def parse_date(value, field_name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a nonempty date string")
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"{field_name} must use MM/DD/YYYY or YYYY-MM-DD")


def parse_money(value):
    if isinstance(value, bool):
        raise ValueError("transaction_amount must be a money string or number")
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        raise ValueError("transaction_amount must be a money string or number")
    cleaned = value.strip().replace("$", "").replace(",", "")
    try:
        return Decimal(cleaned).quantize(MONEY, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"invalid monetary amount: {value!r}") from exc


def money_text(amount):
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def normalized_text(value):
    return value.strip() if isinstance(value, str) else ""


def main(payload):
    if not isinstance(payload, dict):
        return fail("invalid_input", "Input must be a JSON object.")

    requested_card = normalized_text(payload.get("requested_card_type"))
    if not requested_card:
        return fail("missing_requested_card_type", "requested_card_type is required.")

    accounts = payload.get("accounts")
    transactions = payload.get("transactions")
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        return fail("invalid_input", "accounts and transactions must both be arrays.")

    matching_accounts = [
        account for account in accounts
        if isinstance(account, dict)
        and normalized_text(account.get("card_type")) == requested_card
    ]
    if not matching_accounts:
        return fail("card_not_found", "No account matched the requested_card_type exactly.")
    if len(matching_accounts) > 1:
        return fail("ambiguous_card", "More than one account matched the requested_card_type.")
    account = matching_accounts[0]

    scope = payload.get("scope") or {}
    if not isinstance(scope, dict):
        return fail("invalid_scope", "scope must be an object when supplied.")
    mode = scope.get("mode", "last_n")
    if mode not in {"last_n", "date_range", "calendar_month", "all"}:
        return fail("invalid_scope", "scope.mode must be last_n, date_range, calendar_month, or all.")

    statuses = scope.get("statuses", ["COMPLETED"])
    if statuses is not None:
        if not isinstance(statuses, list) or not all(isinstance(x, str) and x.strip() for x in statuses):
            return fail("invalid_scope", "scope.statuses must be null or an array of nonempty strings.")
        statuses = {x.strip().upper() for x in statuses}

    try:
        start = parse_date(scope["start_date"], "scope.start_date") if scope.get("start_date") else None
        end = parse_date(scope["end_date"], "scope.end_date") if scope.get("end_date") else None
        if start and end and start > end:
            return fail("invalid_scope", "scope.start_date cannot be after scope.end_date.")

        month = None
        if mode == "calendar_month":
            raw_month = scope.get("month")
            if not isinstance(raw_month, str):
                return fail("invalid_scope", "calendar_month mode requires scope.month in YYYY-MM format.")
            try:
                month = datetime.strptime(raw_month, "%Y-%m").strftime("%Y-%m")
            except ValueError:
                return fail("invalid_scope", "scope.month must use YYYY-MM format.")

        limit = None
        if mode == "last_n":
            limit = scope.get("limit", 10)
            if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
                return fail("invalid_scope", "scope.limit must be a positive integer for last_n mode.")

        card_records = []
        non_completed_matching_count = 0
        for index, record in enumerate(transactions):
            if not isinstance(record, dict):
                return fail("invalid_transaction", f"transactions[{index}] must be an object.")
            if normalized_text(record.get("credit_card_type")) != requested_card:
                continue
            merchant = normalized_text(record.get("merchant_name"))
            if not merchant:
                return fail("invalid_transaction", f"transactions[{index}].merchant_name is required.")
            transaction_date = parse_date(record.get("transaction_date"), f"transactions[{index}].transaction_date")
            amount = parse_money(record.get("transaction_amount"))
            status = normalized_text(record.get("status"))

            in_scope = True
            if mode == "date_range":
                in_scope = (start is None or transaction_date >= start) and (end is None or transaction_date <= end)
            elif mode == "calendar_month":
                in_scope = transaction_date.strftime("%Y-%m") == month
            if not in_scope:
                continue

            if statuses is not None and status.upper() not in statuses:
                non_completed_matching_count += 1
                continue

            card_records.append({
                "transaction_id": record.get("transaction_id"),
                "date": transaction_date,
                "merchant": merchant,
                "amount": amount,
                "category": normalized_text(record.get("category")) or None,
                "status": status or None,
            })

        card_records.sort(key=lambda item: (item["date"], item["transaction_id"] or ""), reverse=True)
        if limit is not None:
            card_records = card_records[:limit]

        total = sum((item["amount"] for item in card_records), Decimal("0.00"))
        category_totals = defaultdict(lambda: Decimal("0.00"))
        output_records = []
        for item in card_records:
            category_totals[item["category"] or "Uncategorized"] += item["amount"]
            output_records.append({
                "transaction_id": item["transaction_id"],
                "date": item["date"].strftime("%m/%d/%Y"),
                "merchant": item["merchant"],
                "amount": money_text(item["amount"]),
                "category": item["category"],
                "status": item["status"],
            })

        current_balance = account.get("current_balance")
        balance_text = None
        if current_balance is not None:
            balance_text = money_text(parse_money(current_balance))

        scope_output = {"mode": mode, "statuses": sorted(statuses) if statuses is not None else None}
        if start:
            scope_output["start_date"] = start.strftime("%m/%d/%Y")
        if end:
            scope_output["end_date"] = end.strftime("%m/%d/%Y")
        if month:
            scope_output["month"] = month
        if limit is not None:
            scope_output["limit"] = limit

        return {
            "ok": True,
            "card": {
                "card_type": requested_card,
                "account_id": account.get("account_id"),
                "current_balance": balance_text,
            },
            "scope": scope_output,
            "transactions": output_records,
            "transaction_count": len(output_records),
            "total": money_text(total),
            "category_totals": {key: money_text(category_totals[key]) for key in sorted(category_totals)},
            "non_completed_matching_count": non_completed_matching_count,
        }
    except ValueError as exc:
        return fail("invalid_input", str(exc))


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        result = main(incoming)
    except json.JSONDecodeError as exc:
        result = fail("invalid_json", f"Could not parse JSON input: {exc.msg}")
    except Exception as exc:  # Preserve a JSON-only interface for unexpected malformed input.
        result = fail("processing_error", str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
