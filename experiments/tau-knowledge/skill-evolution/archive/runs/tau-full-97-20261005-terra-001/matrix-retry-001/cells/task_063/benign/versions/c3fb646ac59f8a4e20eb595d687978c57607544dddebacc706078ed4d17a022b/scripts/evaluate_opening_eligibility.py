#!/usr/bin/env python3
"""Validate documented personal-savings opening prerequisites.

Input and output are JSON objects on stdin/stdout.  This program is advisory only
and never calls banking tools.
"""
import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def money(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def is_active(account):
    return str(account.get("status", "")).strip().lower() == "active"


def main(payload):
    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        return {"ok": False, "error": "accounts must be a JSON array"}
    today = parse_date(payload.get("as_of"))
    if today is None:
        return {"ok": False, "error": "as_of must be a parseable date or timestamp"}

    blockers = []
    identity_ok = payload.get("identity_verified") is True
    if not identity_ok:
        blockers.append("Identity has not been verified and logged.")

    valid_class = isinstance(payload.get("account_class"), str) and payload["account_class"].strip().endswith("Account")
    if not valid_class:
        blockers.append("The selected account_class must be the full official name ending in 'Account'.")

    active_checking = []
    tenure_checking = []
    savings_count = 0
    collections = []
    negative = []
    malformed = []

    for account in accounts:
        if not isinstance(account, dict):
            malformed.append("An account record is not an object.")
            continue
        kind = str(account.get("account_type", "")).strip().lower()
        aid = str(account.get("account_id", "unknown"))
        status = str(account.get("status", "")).strip().lower()
        if not kind or not status:
            malformed.append("Account %s lacks account_type or status." % aid)
        if status == "collections":
            collections.append(aid)
        balance = money(account.get("balance"))
        if balance is None:
            malformed.append("Account %s has no usable balance." % aid)
        elif balance < 0:
            negative.append(aid)
        if kind == "savings" and account.get("is_personal", True) is not False:
            savings_count += 1
        if kind == "checking" and is_active(account):
            active_checking.append(account)
            opened = parse_date(account.get("date_opened"))
            if opened is None:
                malformed.append("Active checking account %s lacks a usable date_opened." % aid)
            elif (today - opened).days >= 14:
                tenure_checking.append(account)

    if not active_checking:
        blockers.append("No active Rho-Bank checking account was found.")
    elif not tenure_checking:
        blockers.append("No active checking account has the required 14-day tenure.")
    if savings_count >= 5:
        blockers.append("The customer already has %d personal savings accounts (maximum is 5)." % savings_count)
    if collections:
        blockers.append("Accounts in collections were found: %s." % ", ".join(collections))
    if negative:
        blockers.append("Negative balances were found: %s." % ", ".join(negative))
    if malformed:
        blockers.append("Required account data is unresolved: " + " ".join(malformed))

    eligible = not blockers
    funding = {"requested": payload.get("funding_authorized") is True, "ready": False, "blockers": []}
    if funding["requested"]:
        required = money(payload.get("required_opening_deposit"))
        requested = money(payload.get("requested_deposit"))
        source_id = payload.get("source_account_id")
        source = next((a for a in accounts if str(a.get("account_id")) == str(source_id)), None)
        if required is None or required < 0:
            funding["blockers"].append("A valid required opening-deposit amount is needed.")
        if requested is None or requested < 0:
            funding["blockers"].append("A valid requested deposit amount is needed.")
        if required is not None and requested is not None and requested < required:
            funding["blockers"].append("Requested deposit is below the required opening deposit.")
        if not source_id or source is None:
            funding["blockers"].append("An existing source checking account must be selected.")
        elif str(source.get("account_type", "")).lower() != "checking" or not is_active(source):
            funding["blockers"].append("The selected funding source is not an active checking account.")
        elif requested is not None:
            source_balance = money(source.get("balance"))
            if source_balance is None:
                funding["blockers"].append("The selected source account balance is unavailable.")
            elif source_balance < requested:
                funding["blockers"].append("The selected source account does not show enough funds for the requested transfer.")
        funding["ready"] = eligible and not funding["blockers"]

    return {
        "ok": True,
        "eligible_to_open": eligible,
        "checks": {
            "identity_verified": identity_ok,
            "official_account_class": valid_class,
            "active_checking_exists": bool(active_checking),
            "checking_tenure_at_least_14_days": bool(tenure_checking),
            "personal_savings_count": savings_count,
            "under_savings_limit": savings_count < 5,
            "no_collections": not collections,
            "no_negative_balances": not negative
        },
        "eligible_checking_account_ids": [a.get("account_id") for a in tenure_checking],
        "blockers": blockers,
        "immediate_funding": funding
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), default=str))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
