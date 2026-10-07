#!/usr/bin/env python3
"""Validate supplied core banking workflow facts without performing any action.

Input: one JSON object on stdin. See SKILL.md for action-specific schemas.
Output: {"action": str, "allowed": bool, "blockers": [str], "checks": {str: bool}}.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def present(data, key):
    return key in data and data[key] is not None


def as_decimal(value, label, blockers):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        blockers.append(f"{label} must be a valid numeric amount.")
        return None


def require_bool(data, key, expected, blockers, checks):
    if not present(data, key):
        blockers.append(f"Missing required fact: {key}.")
        checks[key] = False
        return False
    actual = data[key]
    ok = actual is expected
    checks[key] = ok
    if not ok:
        wanted = "true" if expected else "false"
        blockers.append(f"{key} must be {wanted}.")
    return ok


def require_number_at_least(data, key, minimum, blockers, checks):
    if not present(data, key):
        blockers.append(f"Missing required fact: {key}.")
        checks[key] = False
        return None
    value = as_decimal(data[key], key, blockers)
    ok = value is not None and value >= Decimal(str(minimum))
    checks[key] = ok
    if value is not None and not ok:
        blockers.append(f"{key} must be at least {minimum}.")
    return value


def require_class_confirmation(data, blockers, checks):
    name = data.get("account_class")
    named = isinstance(name, str) and bool(name.strip())
    confirmed = data.get("official_class_confirmed") is True
    checks["account_class_present"] = named
    checks["official_class_confirmed"] = confirmed
    if not named:
        blockers.append("A non-empty exact official account_class is required.")
    if not confirmed:
        blockers.append("The account_class must be confirmed as the official product name by the customer and product source.")


def status_is_open_or_active(value):
    return isinstance(value, str) and value.strip().upper() in {"OPEN", "ACTIVE"}


def gate_open_checking(data, blockers, checks):
    require_bool(data, "identity_verified", True, blockers, checks)
    require_number_at_least(data, "age", 18, blockers, checks)
    count = require_number_at_least(data, "checking_count_before", 0, blockers, checks)
    if count is not None:
        ok = count + 1 <= 4
        checks["checking_limit_after_open"] = ok
        if not ok:
            blockers.append("Opening would exceed the maximum of four personal checking accounts.")
    require_bool(data, "closed_for_cause_last_6_months", False, blockers, checks)
    require_class_confirmation(data, blockers, checks)


def gate_open_savings(data, blockers, checks):
    require_bool(data, "identity_verified", True, blockers, checks)
    require_bool(data, "active_checking_exists", True, blockers, checks)
    require_number_at_least(data, "checking_tenure_days", 14, blockers, checks)
    count = require_number_at_least(data, "savings_count_before", 0, blockers, checks)
    if count is not None:
        ok = count < 5
        checks["savings_limit_before_open"] = ok
        if not ok:
            blockers.append("Customer already has the maximum of five personal savings accounts.")
    require_bool(data, "has_negative_balance", False, blockers, checks)
    require_bool(data, "has_collections", False, blockers, checks)
    require_class_confirmation(data, blockers, checks)


def gate_close_checking(data, blockers, checks):
    require_bool(data, "identity_verified", True, blockers, checks)
    require_bool(data, "account_owned", True, blockers, checks)
    status = data.get("account_status")
    ok_status = isinstance(status, str) and status.strip().upper() == "OPEN"
    checks["account_status_open"] = ok_status
    if not ok_status:
        blockers.append("Account status must be OPEN for closure.")
    require_bool(data, "has_pending_transactions", False, blockers, checks)
    balance = as_decimal(data.get("balance"), "balance", blockers) if present(data, "balance") else None
    if balance is None and not present(data, "balance"):
        blockers.append("Missing required fact: balance.")
    fee_applies = data.get("fee_applicable")
    if fee_applies is not True and fee_applies is not False:
        checks["fee_applicable_known"] = False
        blockers.append("Missing required fact: fee_applicable.")
        return
    checks["fee_applicable_known"] = True
    if balance is None:
        checks["closure_balance_rule"] = False
        return
    if fee_applies:
        if not present(data, "fee_amount"):
            checks["closure_balance_rule"] = False
            blockers.append("Missing required fact: fee_amount when a closure fee applies.")
            return
        fee = as_decimal(data["fee_amount"], "fee_amount", blockers)
        ok = fee is not None and fee >= 0 and balance >= fee
        checks["closure_balance_rule"] = ok
        if fee is not None and not ok:
            blockers.append("Balance must cover the applicable early-closure fee.")
    else:
        ok = balance == 0
        checks["closure_balance_rule"] = ok
        if not ok:
            blockers.append("Balance must be exactly zero when no early-closure fee applies.")


def gate_transfer(data, blockers, checks):
    require_bool(data, "identity_verified", True, blockers, checks)
    require_bool(data, "customer_authorized", True, blockers, checks)
    require_bool(data, "same_owner", True, blockers, checks)
    source_id = data.get("source_account_id")
    destination_id = data.get("destination_account_id")
    distinct = isinstance(source_id, str) and bool(source_id) and isinstance(destination_id, str) and bool(destination_id) and source_id != destination_id
    checks["distinct_account_ids"] = distinct
    if not distinct:
        blockers.append("Source and destination account IDs must be present and distinct.")
    source_ok = status_is_open_or_active(data.get("source_status"))
    destination_ok = status_is_open_or_active(data.get("destination_status"))
    checks["source_status_open_or_active"] = source_ok
    checks["destination_status_open_or_active"] = destination_ok
    if not source_ok:
        blockers.append("Source account must be ACTIVE or OPEN.")
    if not destination_ok:
        blockers.append("Destination account must be ACTIVE or OPEN.")
    amount = as_decimal(data.get("amount"), "amount", blockers) if present(data, "amount") else None
    available = as_decimal(data.get("source_available_balance"), "source_available_balance", blockers) if present(data, "source_available_balance") else None
    if amount is None and not present(data, "amount"):
        blockers.append("Missing required fact: amount.")
    if available is None and not present(data, "source_available_balance"):
        blockers.append("Missing required fact: source_available_balance.")
    positive = amount is not None and amount > 0
    checks["positive_amount"] = positive
    if amount is not None and not positive:
        blockers.append("Transfer amount must be positive.")
    sufficient = amount is not None and available is not None and amount > 0 and available >= amount
    checks["sufficient_available_balance"] = sufficient
    if amount is not None and available is not None and not sufficient:
        blockers.append("Source available balance must cover the positive transfer amount.")


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"allowed": False, "blockers": [f"Invalid JSON input: {exc.msg}"], "checks": {}}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"allowed": False, "blockers": ["Input must be a JSON object."], "checks": {}}))
        return

    action = data.get("action")
    blockers, checks = [], {}
    gates = {
        "open_checking": gate_open_checking,
        "open_savings": gate_open_savings,
        "close_checking": gate_close_checking,
        "transfer": gate_transfer,
    }
    if action not in gates:
        allowed = ", ".join(sorted(gates))
        print(json.dumps({"action": action, "allowed": False, "blockers": [f"action must be one of: {allowed}."], "checks": {}}))
        return
    gates[action](data, blockers, checks)
    print(json.dumps({"action": action, "allowed": not blockers, "blockers": blockers, "checks": checks}, sort_keys=True))


if __name__ == "__main__":
    main()
