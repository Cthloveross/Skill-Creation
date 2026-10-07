#!/usr/bin/env python3
"""Filter and render a card-specific transaction report from JSON stdin."""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation


def parse_date(value):
    if not isinstance(value, str):
        return datetime.min
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return datetime.min


def clean(value, fallback="Not provided"):
    if value is None or value == "":
        return fallback
    return str(value)


def amount_decimal(value):
    if not isinstance(value, str):
        return None
    cleaned = value.strip().replace("$", "").replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def main(payload):
    card_type = payload.get("card_type")
    if not isinstance(card_type, str) or not card_type.strip():
        raise ValueError("card_type must be a nonempty string")
    card_type = card_type.strip()
    accounts = payload.get("accounts", [])
    transactions = payload.get("transactions", [])
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        raise ValueError("accounts and transactions must be arrays")
    max_items = payload.get("max_items", 25)
    if not isinstance(max_items, int) or max_items < 1:
        raise ValueError("max_items must be a positive integer")

    matching = [
        item for item in transactions
        if isinstance(item, dict) and item.get("credit_card_type") == card_type
    ]
    matching.sort(key=lambda item: parse_date(item.get("transaction_date")), reverse=True)
    shown = matching[:max_items]
    amounts = [amount_decimal(item.get("transaction_amount")) for item in matching]
    valid_amounts = [value for value in amounts if value is not None]
    matched_total = sum(valid_amounts, Decimal("0")) if len(valid_amounts) == len(matching) else None

    balance = None
    for account in accounts:
        if isinstance(account, dict) and account.get("card_type") == card_type:
            balance = account.get("current_balance")
            break

    lines = [f"Here is the matching activity returned for your {card_type}."]
    if balance not in (None, ""):
        lines.append(f"Current balance returned: {clean(balance)}.")
    if not matching:
        lines.append("No matching transactions were returned for this card.")
    else:
        qualifier = f"Showing {len(shown)} of {len(matching)} matching transaction(s), newest first:"
        lines.append(qualifier)
        for item in shown:
            date = clean(item.get("transaction_date"))
            merchant = clean(item.get("merchant_name"))
            amount = clean(item.get("transaction_amount"))
            category = item.get("category")
            status = item.get("status")
            details = []
            if category not in (None, ""):
                details.append(f"Category: {category}")
            if status not in (None, ""):
                details.append(f"Status: {status}")
            suffix = f" — {'; '.join(details)}" if details else ""
            lines.append(f"- {date}: {merchant} — {amount}{suffix}")
    return {
        "card_type": card_type,
        "current_balance": balance,
        "matched_count": len(matching),
        "matched_total": (f"${matched_total:,.2f}" if matched_total is not None else None),
        "shown_count": len(shown),
        "truncated": len(shown) < len(matching),
        "transactions": shown,
        "markdown": "\n".join(lines),
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), ensure_ascii=False))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
