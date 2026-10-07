#!/usr/bin/env python3
"""Validate an account replacement/opening plan from JSON stdin; emit JSON only.

This module makes no external calls and never performs banking actions. See SKILL.md
for the input schema and for required live-record and authorization checks.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def parse_date(value, field, blockers):
    if not isinstance(value, str):
        blockers.append(f"{field} is missing or invalid")
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        blockers.append(f"{field} is missing or invalid")
        return None


def money(value, field, blockers):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        blockers.append(f"{field} is missing or invalid")
        return None
    if not amount.is_finite():
        blockers.append(f"{field} is missing or invalid")
        return None
    return amount


def result(blockers, warnings=None):
    return {
        "allowed": not blockers,
        "blockers": blockers,
        "warnings": warnings or [],
    }


def account_is_active(account):
    return str(account.get("status", "")).upper() in {"ACTIVE", "OPEN"}


def main(payload):
    accounts = payload.get("accounts")
    accounts = accounts if isinstance(accounts, list) else []
    proposed = payload.get("proposed") if isinstance(payload.get("proposed"), dict) else {}
    today_blockers = []
    today = parse_date(payload.get("today"), "today", today_blockers)

    checking_accounts = [a for a in accounts if str(a.get("account_type", "")).lower() == "checking"]
    savings_accounts = [a for a in accounts if str(a.get("account_type", "")).lower() == "savings"]

    opening_common = []
    if not payload.get("identity_verified"):
        opening_common.append("identity is not verified")

    checking_blockers = list(opening_common)
    if proposed.get("open_checking"):
        age = payload.get("customer_age")
        if not isinstance(age, (int, float)) or age < 18:
            checking_blockers.append("customer is not confirmed to be at least 18")
        if len(checking_accounts) >= 4:
            checking_blockers.append("customer already has four personal checking accounts")
        if payload.get("checking_closed_for_cause_last_6_months") is not False:
            checking_blockers.append("checking closure-for-cause status is not confirmed clear")
    checking_result = result(checking_blockers if proposed.get("open_checking") else [])

    savings_blockers = list(opening_common)
    if proposed.get("open_savings"):
        qualifying = []
        if today is None:
            savings_blockers.extend(today_blockers)
        else:
            for account in checking_accounts:
                date_blockers = []
                opened = parse_date(account.get("date_opened"), "checking date_opened", date_blockers)
                if account_is_active(account) and opened is not None and (today - opened).days >= 14:
                    qualifying.append(account)
            if not qualifying:
                savings_blockers.append("no active checking account is confirmed to have at least 14 days tenure")
        if len(savings_accounts) >= 5:
            savings_blockers.append("customer already has five personal savings accounts")
        if payload.get("has_collections") is not False:
            savings_blockers.append("collections status is not confirmed clear")
        if payload.get("has_negative_balance") is not False:
            savings_blockers.append("negative-balance status is not confirmed clear")
    savings_result = result(savings_blockers if proposed.get("open_savings") else [])

    close_id = proposed.get("close_account_id")
    closure_blockers, closure_warnings = [], []
    closure_account = next((a for a in accounts if a.get("account_id") == close_id), None)
    if close_id is not None:
        if closure_account is None:
            closure_blockers.append("closure account was not found")
        else:
            if str(closure_account.get("status", "")).upper() != "OPEN":
                closure_blockers.append("account status is not OPEN")
            if closure_account.get("has_pending_transactions") is not False:
                closure_blockers.append("pending-transaction status is not confirmed clear")
            balance = money(closure_account.get("balance"), "closure account balance", closure_blockers)
            class_name = closure_account.get("account_class")
            if class_name == "Light Blue Account":
                if today is None:
                    closure_blockers.extend(today_blockers)
                else:
                    opened = parse_date(closure_account.get("date_opened"), "closure account date_opened", closure_blockers)
                    if opened is not None:
                        age_days = (today - opened).days
                        if age_days < 0:
                            closure_blockers.append("closure account opening date is in the future")
                        elif age_days < 30:
                            if balance is not None and balance < Decimal("15"):
                                closure_blockers.append("Light Blue early-closure fee is $15 and balance is insufficient")
                            else:
                                closure_warnings.append("$15 Light Blue early-closure fee applies")
                        elif balance is not None and balance != Decimal("0"):
                            closure_blockers.append("account balance must be $0 when no early-closure fee applies")
            elif balance is not None and balance != Decimal("0"):
                closure_warnings.append("verify tier-specific fee and balance rules before closure")
    closure_result = result(closure_blockers, closure_warnings) if close_id is not None else result([])

    transfer = proposed.get("transfer")
    transfer_blockers = []
    if transfer is not None:
        if not isinstance(transfer, dict):
            transfer_blockers.append("transfer details are invalid")
        else:
            source_id = transfer.get("source_account_id")
            destination_id = transfer.get("destination_account_id")
            source = next((a for a in accounts if a.get("account_id") == source_id), None)
            destination = next((a for a in accounts if a.get("account_id") == destination_id), None)
            if not transfer.get("customer_authorized"):
                transfer_blockers.append("customer has not authorized the transfer")
            if not source_id or not destination_id or source_id == destination_id:
                transfer_blockers.append("source and destination must be distinct valid account IDs")
            if source is None or destination is None:
                transfer_blockers.append("source or destination account was not found")
            else:
                if not account_is_active(source) or not account_is_active(destination):
                    transfer_blockers.append("both transfer accounts must be ACTIVE or OPEN")
                amount = money(transfer.get("amount"), "transfer amount", transfer_blockers)
                source_balance = money(source.get("balance"), "source balance", transfer_blockers)
                if amount is not None and amount <= 0:
                    transfer_blockers.append("transfer amount must be positive")
                if amount is not None and source_balance is not None and amount > source_balance:
                    transfer_blockers.append("source account has insufficient funds")
    transfer_result = result(transfer_blockers) if transfer is not None else result([])

    sequence = []
    if proposed.get("open_checking"):
        sequence.append("open replacement checking after checking-opening eligibility passes")
    if proposed.get("open_savings"):
        sequence.append("open savings while an existing qualifying checking account remains active")
    if transfer is not None:
        sequence.append("perform authorized savings funding transfer only after both accounts exist and transfer validation passes")
    if close_id is not None:
        sequence.append("close the former checking account last, only after closure validation passes")

    return {
        "checking_opening": checking_result,
        "savings_opening": savings_result,
        "closure": closure_result,
        "transfer": transfer_result,
        "safe_sequence": sequence,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON value must be an object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
