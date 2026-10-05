#!/usr/bin/env python3
"""Deterministic preflight checklist for bank-account actions.

Reads one JSON object from stdin and writes one JSON object to stdout. It does
not retrieve records, perform banking actions, or make a product eligible.
"""

import json
import sys
from typing import Any, Dict, List


def is_true(mapping: Dict[str, Any], key: str) -> bool:
    return mapping.get(key) is True


def require_true(mapping: Dict[str, Any], key: str, label: str, blockers: List[str]) -> None:
    if not is_true(mapping, key):
        blockers.append(label)


def main() -> None:
    try:
        raw = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"allowed": False, "blockers": ["invalid JSON input: " + str(exc)], "required_checks": []}))
        return

    if not isinstance(raw, dict):
        print(json.dumps({"allowed": False, "blockers": ["input must be a JSON object"], "required_checks": []}))
        return

    action = raw.get("action")
    blockers: List[str] = []
    required: List[str] = [
        "identity_verified from approved record verification",
        "authority_verified",
        "eligibility_verified from authoritative records",
    ]

    require_true(raw, "identity_verified", "identity has not been verified", blockers)
    require_true(raw, "authority_verified", "authority has not been verified", blockers)
    require_true(raw, "eligibility_verified", "product eligibility has not been verified", blockers)

    if action in ("checking_open", "savings_open"):
        required.extend(["exact account_class", "customer_authorized"])
        if not isinstance(raw.get("account_class"), str) or not raw["account_class"].strip():
            blockers.append("exact official account class is missing")
        require_true(raw, "customer_authorized", "customer has not explicitly authorized account opening", blockers)

    if action == "checking_open":
        checking = raw.get("checking") if isinstance(raw.get("checking"), dict) else {}
        required.extend([
            "age_18_or_over",
            "checking_count_at_most_4",
            "no_for_cause_closure_last_6_months",
        ])
        require_true(checking, "age_18_or_over", "customer is not verified as age 18 or older", blockers)
        require_true(checking, "checking_count_at_most_4", "checking-account limit has not been met", blockers)
        require_true(checking, "no_for_cause_closure_last_6_months", "for-cause closure requirement has not been met", blockers)

    elif action == "savings_open":
        savings = raw.get("savings") if isinstance(raw.get("savings"), dict) else {}
        required.extend([
            "active_checking_exists",
            "checking_tenure_at_least_14_days",
            "savings_count_fewer_than_5",
            "no_collections_or_negative_balances",
        ])
        require_true(savings, "active_checking_exists", "no active checking account has been verified", blockers)
        require_true(savings, "checking_tenure_at_least_14_days", "checking tenure of at least 14 days has not been verified", blockers)
        require_true(savings, "savings_count_fewer_than_5", "savings-account limit has not been met", blockers)
        require_true(savings, "no_collections_or_negative_balances", "account standing requirement has not been met", blockers)

    elif action == "transfer":
        transfer = raw.get("transfer") if isinstance(raw.get("transfer"), dict) else {}
        required.extend([
            "source_id and destination_id are distinct",
            "same_customer_ownership_verified",
            "both_accounts_active_or_open",
            "available_funds_verified",
            "positive USD amount",
            "minimum_opening_deposit_verified when funding a new savings account",
            "transfer_authorized",
        ])
        source = transfer.get("source_id")
        destination = transfer.get("destination_id")
        if not isinstance(source, str) or not source.strip():
            blockers.append("source account ID is missing")
        if not isinstance(destination, str) or not destination.strip():
            blockers.append("destination account ID is missing")
        if isinstance(source, str) and isinstance(destination, str) and source.strip() == destination.strip():
            blockers.append("source and destination account IDs must be distinct")
        require_true(transfer, "same_customer_ownership_verified", "same-customer account ownership has not been verified", blockers)
        require_true(transfer, "both_accounts_active_or_open", "both accounts have not been verified as ACTIVE or OPEN", blockers)
        require_true(transfer, "available_funds_verified", "sufficient available funds have not been verified", blockers)
        amount = transfer.get("amount_usd")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount <= 0:
            blockers.append("transfer amount must be a positive USD number")
        require_true(transfer, "minimum_opening_deposit_verified", "opening-deposit requirement has not been verified", blockers)
        require_true(transfer, "transfer_authorized", "customer has not explicitly authorized the transfer", blockers)

    else:
        blockers.append("action must be checking_open, savings_open, or transfer")

    print(json.dumps({
        "allowed": not blockers,
        "blockers": blockers,
        "required_checks": required,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
