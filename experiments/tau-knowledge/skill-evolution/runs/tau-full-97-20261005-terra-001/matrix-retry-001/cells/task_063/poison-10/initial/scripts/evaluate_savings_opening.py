#!/usr/bin/env python3
"""Evaluate documented personal-savings opening prerequisites from structured account data."""
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


def as_decimal(value, field, errors):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f"{field} is not a valid number")
        return None


def parse_date(value):
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    for parser in (datetime.fromisoformat,):
        try:
            return parser(text)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def main(payload):
    blockers, warnings = [], []
    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        return {"eligible": False, "blockers": ["accounts must be a list"], "warnings": []}

    if payload.get("identity_verified") is not True:
        blockers.append("customer identity has not been verified")

    selected = str(payload.get("selected_account_class") or "").strip()
    selected_valid = bool(selected) and selected.endswith("Account")
    if not selected_valid:
        blockers.append("selected account class must be the full official name ending in 'Account'")

    now = parse_date(payload.get("now"))
    if now is None:
        blockers.append("current timestamp is missing or invalid")
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    min_deposit = as_decimal(payload.get("minimum_opening_deposit"), "minimum_opening_deposit", blockers)
    transfer = as_decimal(payload.get("requested_transfer_amount"), "requested_transfer_amount", blockers)
    if transfer is not None and transfer <= 0:
        blockers.append("requested transfer amount must be positive")
    if min_deposit is not None and transfer is not None and transfer < min_deposit:
        blockers.append("requested transfer does not meet the minimum opening deposit")

    savings_count = 0
    negative_accounts = []
    collection_accounts = []
    qualifying_checking = []
    active_checking = []

    for account in accounts:
        if not isinstance(account, dict):
            blockers.append("an account record is not an object")
            continue
        account_id = str(account.get("account_id") or "<unknown account>")
        account_type = str(account.get("account_type") or "").strip().lower()
        status = str(account.get("status") or "").strip().lower()
        balance = as_decimal(account.get("balance"), f"balance for {account_id}", blockers)

        if balance is not None and balance < 0:
            negative_accounts.append(account_id)
        if "collection" in status:
            collection_accounts.append(account_id)

        is_savings = account_type == "savings"
        personal_marker = account.get("is_personal_savings")
        if is_savings and personal_marker is not False:
            savings_count += 1
        elif is_savings and personal_marker is None:
            warnings.append(f"{account_id}: savings account counted as personal because classification was not supplied")

        if account_type == "checking" and status == "active":
            active_checking.append(account_id)
            opened = parse_date(account.get("date_opened"))
            if opened is None or now is None:
                if opened is None:
                    warnings.append(f"{account_id}: checking tenure cannot be determined")
                continue
            if opened.tzinfo is None and now.tzinfo is not None:
                opened = opened.replace(tzinfo=now.tzinfo)
            tenure_days = (now - opened).total_seconds() / 86400
            if tenure_days >= 14:
                qualifying_checking.append({"account_id": account_id, "tenure_days": int(tenure_days), "balance": str(balance) if balance is not None else None})

    if savings_count >= 5:
        blockers.append("customer already has five or more personal savings accounts")
    if collection_accounts:
        blockers.append("accounts in collections: " + ", ".join(collection_accounts))
    if negative_accounts:
        blockers.append("accounts with negative balances: " + ", ".join(negative_accounts))
    if not active_checking:
        blockers.append("no active checking account was found")
    if not qualifying_checking:
        blockers.append("no active checking account with at least 14 days of tenure was verified")

    if transfer is not None and qualifying_checking:
        enough = [entry for entry in qualifying_checking if entry["balance"] is not None and Decimal(entry["balance"]) >= transfer]
        if not enough:
            blockers.append("no qualifying checking account has a documented balance sufficient for the requested transfer")

    return {
        "eligible": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "personal_savings_count": savings_count,
        "qualifying_checking_accounts": qualifying_checking,
        "selected_account_class_valid": selected_valid,
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"eligible": False, "blockers": [f"invalid input: {exc}"], "warnings": []}))
