#!/usr/bin/env python3
"""Validate a credit-card dispute contact checklist.

Reads one JSON object from stdin and writes one JSON object to stdout.
This utility only prepares information for a customer-support conversation.
"""

import json
import sys

CHANNELS = {
    "phone": "1-800-RHO-BANK",
    "mobile_app": "Rho-Bank mobile-app chat",
    "online_help_center": "rhobank.com/help",
}

ALIASES = {
    "fraud": "unauthorized_or_fraudulent_charge",
    "unauthorized": "unauthorized_or_fraudulent_charge",
    "unauthorized charge": "unauthorized_or_fraudulent_charge",
    "fraudulent": "unauthorized_or_fraudulent_charge",
    "fraudulent charge": "unauthorized_or_fraudulent_charge",
    "unauthorized_or_fraudulent_charge": "unauthorized_or_fraudulent_charge",
    "duplicate": "duplicate_charge",
    "duplicate charge": "duplicate_charge",
    "duplicate_charge": "duplicate_charge",
    "incorrect amount": "incorrect_amount",
    "incorrect_amount": "incorrect_amount",
    "goods not received": "goods_or_services_not_received",
    "services not received": "goods_or_services_not_received",
    "goods or services not received": "goods_or_services_not_received",
    "goods_or_services_not_received": "goods_or_services_not_received",
    "not as described": "item_not_as_described",
    "item not as described": "item_not_as_described",
    "item_not_as_described": "item_not_as_described",
    "cancelled subscription": "cancelled_subscription_still_charging",
    "cancelled subscription still charging": "cancelled_subscription_still_charging",
    "cancelled_subscription_still_charging": "cancelled_subscription_still_charging",
    "missing refund": "refund_never_processed",
    "refund never processed": "refund_never_processed",
    "refund_never_processed": "refund_never_processed",
}

REQUIRED = ("account_reference", "merchant", "amount", "purchase_date", "issue_type")


def nonempty(value):
    return isinstance(value, (str, int, float)) and str(value).strip() != ""


def normalize_issue(value):
    if not isinstance(value, str):
        return None
    key = " ".join(value.strip().lower().replace("-", " ").split())
    return ALIASES.get(key) or ALIASES.get(key.replace(" ", "_"))


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        json.dump({"valid": False, "error": "Input must be a JSON object.", "detail": str(exc)}, sys.stdout)
        return

    if not isinstance(payload, dict):
        json.dump({"valid": False, "error": "Input must be a JSON object."}, sys.stdout)
        return

    transactions = payload.get("transactions")
    problems = []
    normalized = []
    if not isinstance(transactions, list) or not transactions:
        problems.append({"field": "transactions", "problem": "Provide at least one disputed transaction in an array."})
        transactions = []

    for index, txn in enumerate(transactions):
        prefix = "transactions[{}]".format(index)
        if not isinstance(txn, dict):
            problems.append({"field": prefix, "problem": "Each transaction must be an object."})
            continue
        for field in REQUIRED:
            if not nonempty(txn.get(field)):
                problems.append({"field": prefix + "." + field, "problem": "This field is required."})
        issue = normalize_issue(txn.get("issue_type"))
        if nonempty(txn.get("issue_type")) and issue is None:
            problems.append({
                "field": prefix + ".issue_type",
                "problem": "Use a documented dispute category or supported alias.",
            })
        normalized.append({
            "account_reference": txn.get("account_reference"),
            "merchant": txn.get("merchant"),
            "amount": txn.get("amount"),
            "purchase_date": txn.get("purchase_date"),
            "issue_type": issue,
            "desired_resolution": txn.get("desired_resolution"),
            "merchant_contacted": txn.get("merchant_contacted"),
        })

    account_ready = payload.get("account_information_ready")
    checklist = [
        "Have account information ready.",
        "For each disputed transaction, have the purchase date, merchant name, and amount ready.",
        "Explain the dispute reason and the requested resolution for each transaction.",
        "For non-fraud issues, be ready to explain whether you contacted the merchant and the result.",
    ]
    if account_ready is False:
        checklist.insert(0, "Account information is not currently marked ready; customer support can explain its filing requirements.")

    output = {
        "valid": not problems,
        "missing_or_invalid": problems,
        "support_channels": CHANNELS,
        "preparation_checklist": checklist,
        "transactions": normalized,
        "note": "This output is a preparation aid only. It does not submit disputes or promise any outcome.",
    }
    json.dump(output, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
