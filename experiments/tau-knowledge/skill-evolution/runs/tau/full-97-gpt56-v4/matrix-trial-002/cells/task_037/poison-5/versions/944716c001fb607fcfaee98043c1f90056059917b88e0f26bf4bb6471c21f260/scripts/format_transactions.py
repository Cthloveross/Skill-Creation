#!/usr/bin/env python3
"""Filter and format recent credit-card transactions.

Input: JSON object described in SKILL.md.
Output: {"ok": bool, "count": int, "transactions": list, "message": str,
         "warnings": list} on stdout. Errors are represented as ok=false.
"""
import json
import sys
from datetime import datetime


def fail(message):
    return {"ok": False, "count": 0, "transactions": [], "message": "", "warnings": [message]}


def parse_date(value):
    if not isinstance(value, str):
        return None
    for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), pattern)
        except ValueError:
            pass
    return None


def clean(value, fallback="Not available"):
    if value is None or value == "":
        return fallback
    return str(value)


def main(data):
    if not isinstance(data, dict):
        return fail("Input must be a JSON object.")
    card_type = data.get("card_type")
    if not isinstance(card_type, str) or not card_type.strip():
        return fail("card_type must be a non-empty exact card type.")
    source = data.get("transactions")
    if not isinstance(source, list):
        return fail("transactions must be a JSON array.")
    limit = data.get("limit", 10)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        return fail("limit must be a positive integer.")

    selected = []
    warnings = []
    for index, transaction in enumerate(source):
        if not isinstance(transaction, dict):
            warnings.append("Ignored a non-object transaction record at position %d." % (index + 1))
            continue
        if transaction.get("credit_card_type") != card_type:
            continue
        copied = dict(transaction)
        parsed = parse_date(copied.get("transaction_date"))
        if parsed is None:
            warnings.append("A selected transaction has a missing or unrecognized date and was placed after dated records.")
        selected.append((parsed, index, copied))

    # Stable tie handling preserves source order for records on the same date.
    selected.sort(key=lambda item: (item[0] is not None, item[0] or datetime.min), reverse=True)
    records = [item[2] for item in selected[:limit]]
    include_rewards = bool(data.get("include_rewards", False))

    lines = []
    balance = data.get("current_balance")
    heading = "Here are the %d most recent transaction%s on your %s" % (
        len(records), "s" if len(records) != 1 else "", card_type.strip())
    if isinstance(balance, str) and balance.strip():
        heading += ". The current balance is %s" % balance.strip()
    heading += "."
    lines.append(heading)

    if records:
        for record in records:
            line = "- {date}: {merchant} — {amount} ({category}; {status})".format(
                date=clean(record.get("transaction_date")),
                merchant=clean(record.get("merchant_name")),
                amount=clean(record.get("transaction_amount")),
                category=clean(record.get("category")),
                status=clean(record.get("status")),
            )
            if include_rewards:
                line += "; rewards: %s" % clean(record.get("rewards_earned"))
            lines.append(line)
    else:
        lines.append("No transactions were found for that card in the supplied records.")

    lines.append("Let me know if you would like older activity or want to review a specific charge.")
    return {"ok": True, "count": len(records), "transactions": records,
            "message": "\n".join(lines), "warnings": warnings}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        result = main(payload)
    except json.JSONDecodeError:
        result = fail("stdin must contain valid JSON.")
    except Exception as exc:  # Keep the executable interface machine-readable.
        result = fail("Unexpected formatter error: %s" % exc)
    print(json.dumps(result, ensure_ascii=False))
