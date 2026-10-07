#!/usr/bin/env python3
"""Validate supplied prerequisites for a proposed internal card payment.

Reads one JSON object from stdin and writes one JSON result to stdout. It is
purely advisory: it does not call bank tools or persist data.
"""
import json
import math
import sys


def is_nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        print(json.dumps({"ready": False, "issues": ["Input must be a JSON object: " + str(exc)]}))
        return

    if not isinstance(data, dict):
        print(json.dumps({"ready": False, "issues": ["Input must be a JSON object."]}))
        return

    issues = []
    if data.get("identity_verified") is not True:
        issues.append("Customer identity has not been verified and logged.")
    if data.get("authorization_confirmed") is not True:
        issues.append("Exact payment authorization has not been confirmed.")

    for field, label in (
        ("user_id", "Customer user ID"),
        ("checking_account_id", "Selected checking account ID"),
        ("credit_card_account_id", "Target credit-card account ID"),
    ):
        if not is_nonempty_string(data.get(field)):
            issues.append(label + " is missing.")

    amount = data.get("amount")
    checking = data.get("checking_available_balance")
    card = data.get("credit_card_outstanding_balance")
    if not finite_number(amount) or float(amount) <= 0:
        issues.append("Payment amount must be a positive finite number.")
    if not finite_number(checking) or float(checking) < 0:
        issues.append("Current available checking balance is missing or invalid.")
    if not finite_number(card) or float(card) < 0:
        issues.append("Current credit-card outstanding balance is missing or invalid.")

    if finite_number(amount) and finite_number(checking) and float(amount) > float(checking):
        issues.append("Payment amount exceeds the available checking balance.")
    if finite_number(amount) and finite_number(card) and float(amount) > float(card):
        issues.append("Payment amount exceeds the credit-card outstanding balance.")

    output = {"ready": not issues, "issues": issues}
    if not issues:
        output["post_payment_balances"] = {
            "checking": round(float(checking) - float(amount), 2),
            "credit_card": round(float(card) - float(amount), 2),
        }
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
