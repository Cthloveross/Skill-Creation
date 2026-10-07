#!/usr/bin/env python3
"""Conservative account-opening and closure eligibility assessment.

Reads JSON from stdin and emits JSON to stdout.  This helper is read-only and
makes no banking-tool calls.
"""
import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation


def parse_time(value):
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    candidates = (value, value.replace("Z", "+00:00"))
    for candidate in candidates:
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            pass
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def decimal_value(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def norm(value):
    return str(value or "").strip().upper()


def normalize_account(account):
    """Accept canonical fields and the documented retrieval field aliases."""
    if not isinstance(account, dict):
        return account
    item = dict(account)
    if not item.get("account_type"):
        item["account_type"] = item.get("class")
    if not item.get("account_class"):
        item["account_class"] = item.get("level")
    if item.get("balance") is None:
        item["balance"] = item.get("current_holdings")
    return item


def tier_for(account_class):
    classes = {
        "LIGHT BLUE ACCOUNT": (30, Decimal("15"), 0),
        "LIGHT GREEN ACCOUNT": (30, Decimal("15"), 0),
        "GREEN FEE-FREE ACCOUNT": (30, Decimal("15"), 0),
        "BLUE ACCOUNT": (60, Decimal("25"), 3),
        "GREEN ACCOUNT": (60, Decimal("25"), 3),
        "EVERGREEN ACCOUNT": (90, Decimal("50"), 7),
        "BLUEST ACCOUNT": (180, Decimal("100"), 14),
    }
    return classes.get(norm(account_class))


def main(payload):
    now = parse_time(payload.get("now"))
    raw_accounts = payload.get("accounts")
    accounts = [normalize_account(a) for a in raw_accounts] if isinstance(raw_accounts, list) else []
    result = {
        "savings_opening": {"eligible": False, "blockers": [], "unknown_fields": []},
        "closure": {"eligible": False, "blockers": [], "unknown_fields": []},
    }

    opening = result["savings_opening"]
    if now is None:
        opening["unknown_fields"].append("now")
    if not isinstance(raw_accounts, list):
        opening["unknown_fields"].append("accounts")
    if payload.get("identity_verified") is not True:
        opening["blockers"].append("identity has not been verified")
    selected_class = payload.get("selected_account_class")
    if not isinstance(selected_class, str) or not selected_class.strip():
        opening["unknown_fields"].append("selected_account_class")
    elif not selected_class.strip().endswith("Account"):
        opening["blockers"].append("selected account class must end with Account")

    active_eligible_checkings = 0
    savings_count = 0
    for account in accounts:
        if not isinstance(account, dict):
            opening["unknown_fields"].append("account record")
            continue
        account_type = norm(account.get("account_type"))
        status = norm(account.get("status"))
        if account_type == "SAVINGS" and status != "CLOSED":
            savings_count += 1
        balance = decimal_value(account.get("balance"))
        if balance is None:
            opening["unknown_fields"].append("balance for " + str(account.get("account_id", "unknown account")))
        elif balance < 0:
            opening["blockers"].append("negative balance on " + str(account.get("account_id", "unknown account")))
        if account.get("in_collections") is True or "COLLECTION" in status:
            opening["blockers"].append("collections status on " + str(account.get("account_id", "unknown account")))
        if account_type == "CHECKING" and status == "OPEN":
            opened = parse_time(account.get("date_opened"))
            if opened is None or now is None:
                opening["unknown_fields"].append("checking opening date for " + str(account.get("account_id", "unknown account")))
            elif now - opened >= timedelta(days=14):
                active_eligible_checkings += 1

    if active_eligible_checkings == 0 and not opening["unknown_fields"]:
        opening["blockers"].append("no active checking account held at least 14 days")
    if savings_count >= 5:
        opening["blockers"].append("five-account personal savings limit reached")
    opening["savings_count"] = savings_count
    opening["qualifying_checking_count"] = active_eligible_checkings
    opening["eligible"] = not opening["blockers"] and not opening["unknown_fields"]

    closure = result["closure"]
    target_id = payload.get("target_account_id")
    target = next((a for a in accounts if isinstance(a, dict) and a.get("account_id") == target_id), None)
    if not target_id:
        closure["unknown_fields"].append("target_account_id")
    elif target is None:
        closure["blockers"].append("closure target not found in supplied accounts")
    else:
        if norm(target.get("account_type")) != "CHECKING":
            closure["blockers"].append("target is not a checking account")
        if norm(target.get("status")) != "OPEN":
            closure["blockers"].append("target status is not OPEN")
        policy = tier_for(target.get("account_class"))
        if policy is None:
            closure["unknown_fields"].append("closure tier for account class")
        opened = parse_time(target.get("date_opened"))
        balance = decimal_value(target.get("balance"))
        if now is None:
            closure["unknown_fields"].append("now")
        if opened is None:
            closure["unknown_fields"].append("target date_opened")
        if balance is None:
            closure["unknown_fields"].append("target balance")
        if policy is not None and now is not None and opened is not None and balance is not None:
            window, fee, notice_days = policy
            fee_applies = now - opened < timedelta(days=window)
            required_balance = fee if fee_applies else Decimal("0")
            closure.update({"fee_applies": fee_applies, "fee": str(fee) if fee_applies else "0", "notice_days": notice_days})
            if fee_applies and balance < fee:
                closure["blockers"].append("balance is below required early-closure fee")
            if not fee_applies and balance != 0:
                closure["blockers"].append("balance must be exactly zero when no early-closure fee applies")
            notice_at = parse_time(payload.get("closure_notice_given_at"))
            if notice_days and notice_at is None:
                closure["blockers"].append("required closure notice has not been recorded")
            elif notice_at is not None and now < notice_at + timedelta(days=notice_days):
                closure["blockers"].append("required closure notice period has not elapsed")
                closure["earliest_closure_at"] = (notice_at + timedelta(days=notice_days)).isoformat()

    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        closure["unknown_fields"].append("transactions")
    elif any(isinstance(tx, dict) and norm(tx.get("status")) == "PENDING" for tx in transactions):
        closure["blockers"].append("target has pending transactions")
    closure["eligible"] = not closure["blockers"] and not closure["unknown_fields"]

    if payload.get("funding_deferred") is True:
        if now is None:
            result["funding_deadline"] = None
            result.setdefault("unknown_fields", []).append("now required for funding deadline")
        else:
            result["funding_deadline"] = (now + timedelta(days=30)).isoformat()
    return result


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
