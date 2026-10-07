#!/usr/bin/env python3
"""Summarize structured account-activity facts for debit-card decline diagnosis.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper is
read-only: it does not call banking tools, access external files, or decide whether a
banking action may be taken.
"""
import json
import math
import sys


def finite_number(value, field, errors):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{field} must be a number")
        return None
    value = float(value)
    if not math.isfinite(value):
        errors.append(f"{field} must be finite")
        return None
    return value


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"errors": [f"invalid JSON: {exc.msg}"]}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"errors": ["top-level JSON value must be an object"]}))
        return

    errors = []
    purchase = None
    balance = None
    available = None
    if "purchase_amount" in data:
        purchase = finite_number(data["purchase_amount"], "purchase_amount", errors)
        if purchase is not None and purchase < 0:
            errors.append("purchase_amount must not be negative")
    if "account_balance" in data:
        balance = finite_number(data["account_balance"], "account_balance", errors)
    if "available_balance" in data:
        available = finite_number(data["available_balance"], "available_balance", errors)

    transactions = data.get("transactions", [])
    if not isinstance(transactions, list):
        errors.append("transactions must be an array")
        transactions = []

    pending_debits = []
    pending_credits = []
    check_deposit_candidates = []
    for index, tx in enumerate(transactions):
        if not isinstance(tx, dict):
            errors.append(f"transactions[{index}] must be an object")
            continue
        amount = finite_number(tx.get("amount"), f"transactions[{index}].amount", errors)
        status = tx.get("status")
        if status not in ("pending", "posted"):
            errors.append(f"transactions[{index}].status must be 'pending' or 'posted'")
            continue
        if amount is None:
            continue
        tx_type = tx.get("type", "")
        description = tx.get("description", "")
        if not isinstance(tx_type, str) or not isinstance(description, str):
            errors.append(f"transactions[{index}] type and description must be strings when supplied")
            continue
        compact = {"index": index, "amount": round(amount, 2), "type": tx_type, "description": description, "date": tx.get("date")}
        if status == "pending" and amount < 0:
            pending_debits.append(compact)
        if status == "pending" and amount > 0:
            pending_credits.append(compact)
        if tx_type in ("check_deposit", "mobile_deposit"):
            check_deposit_candidates.append({**compact, "status": status})

    pending_debit_total = round(sum(-item["amount"] for item in pending_debits), 2)
    output = {
        "errors": errors,
        "pending_debit_total": pending_debit_total,
        "pending_debit_count": len(pending_debits),
        "pending_credit_count": len(pending_credits),
        "pending_debits": pending_debits,
        "check_deposit_candidates": check_deposit_candidates,
        "comparisons": {},
        "cautions": [
            "Pending debits reduce available funds.",
            "Authorization holds may reduce available balance without appearing in transaction history.",
            "A check deposit appearing in history does not by itself establish that its funds are available."
        ]
    }
    reference_balance = available if available is not None else balance
    if purchase is not None and reference_balance is not None:
        output["comparisons"]["purchase_exceeds_reported_balance"] = purchase > reference_balance
        output["comparisons"]["reported_balance_after_pending_debits"] = round(reference_balance - pending_debit_total, 2)
        output["comparisons"]["purchase_exceeds_balance_after_pending_debits"] = purchase > (reference_balance - pending_debit_total)
        output["comparisons"]["balance_source"] = "available_balance" if available is not None else "account_balance"
    if data.get("overdraft_pos_enabled") is False:
        output["cautions"].append("POS overdraft coverage is reported as disabled; do not assume it will cover a debit-card purchase.")
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
