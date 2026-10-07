#!/usr/bin/env python3
"""Format a selected credit-card account and its recent transactions.

Input JSON on stdin:
  card_type: exact requested card type (required)
  accounts_result: verbatim result string from get_credit_card_accounts_by_user
  transactions_result: verbatim result string from get_credit_card_transactions_by_user
  limit: optional positive integer, default 10
Output JSON: {ok, card_type, card, transactions, shown_count,
              total_matching_count}, or {ok:false,error}.
"""
import json
import re
import sys
from datetime import datetime

FIELD_RE = re.compile(r"^\s{3}([a-z_]+):\s*(.*?)\s*$", re.MULTILINE)
RECORD_RE = re.compile(r"^\s*\d+\. Record ID: ([^\n]+)\n(.*?)(?=^\s*\d+\. Record ID:|\Z)", re.MULTILINE | re.DOTALL)


def records(text):
    if not isinstance(text, str):
        raise ValueError("tool results must be strings")
    out = []
    for match in RECORD_RE.finditer(text):
        item = {"record_id": match.group(1).strip()}
        for key, value in FIELD_RE.findall(match.group(2)):
            item[key] = value.strip()
        out.append(item)
    return out


def date_key(item):
    value = item.get("transaction_date", "")
    try:
        return datetime.strptime(value, "%m/%d/%Y")
    except ValueError:
        return datetime.min


def main():
    try:
        data = json.load(sys.stdin)
        card_type = data.get("card_type")
        if not isinstance(card_type, str) or not card_type.strip():
            raise ValueError("card_type is required")
        card_type = card_type.strip()
        limit = data.get("limit", 10)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("limit must be a positive integer")

        accounts = records(data.get("accounts_result"))
        selected = [a for a in accounts if a.get("card_type") == card_type]
        if not selected:
            raise ValueError("selected card type was not found in account results")
        if len(selected) > 1:
            raise ValueError("more than one account has the selected card type")

        matching = [t for t in records(data.get("transactions_result"))
                    if t.get("credit_card_type") == card_type]
        required = ("merchant_name", "transaction_amount", "transaction_date", "status")
        incomplete = [t.get("transaction_id", t["record_id"]) for t in matching
                      if any(not t.get(k) for k in required)]
        if incomplete:
            raise ValueError("matching transaction records are incomplete")
        matching.sort(key=date_key, reverse=True)
        shown = matching[:limit]
        output = {
            "ok": True,
            "card_type": card_type,
            "card": selected[0],
            "transactions": shown,
            "shown_count": len(shown),
            "total_matching_count": len(matching),
        }
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        output = {"ok": False, "error": str(exc)}
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
