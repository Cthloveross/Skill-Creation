#!/usr/bin/env python3
"""Advisory calculations for debit-card purchase-decline investigation.
Reads one JSON object from stdin and emits one JSON object on stdout.
"""
import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation


def parse_date(value):
    if value is None or value == "":
        return None
    text = str(value).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def amount(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def out_money(value):
    return None if value is None else float(value.quantize(Decimal("0.01")))


def add_unique(items, value):
    if value not in items:
        items.append(value)


def main(data):
    errors, missing, findings = [], [], []
    account = data.get("account") if isinstance(data.get("account"), dict) else {}
    card = data.get("card") if isinstance(data.get("card"), dict) else {}
    txns = data.get("transactions")
    if not isinstance(txns, list):
        errors.append("transactions must be an array")
        txns = []
    today = parse_date(data.get("current_time"))
    if today is None:
        errors.append("current_time must be a parseable date or timestamp")
    attempted = amount(data.get("attempted_amount"))
    if data.get("attempted_amount") is not None and attempted is None:
        errors.append("attempted_amount must be numeric")

    status, card_status = account.get("status"), card.get("status")
    if not status: add_unique(missing, "linked checking account status")
    if not card_status: add_unique(missing, "debit card status")
    if card_status:
        findings.append({"priority": 1, "kind": "card_status", "result": str(card_status).lower()})
    if status:
        findings.append({"priority": 2, "kind": "account_status", "result": str(status).lower()})

    if card.get("fraud_alert_active") is True:
        source = card.get("alert_source")
        if source == "bank_initiated":
            findings.append({"priority": 3, "kind": "fraud_alert", "result": "bank_initiated", "next_step": "Do not clear; transfer to security."})
        elif source == "customer_initiated":
            findings.append({"priority": 3, "kind": "fraud_alert", "result": "customer_initiated", "next_step": "Clear only after verification and legitimacy confirmation."})
        else: add_unique(missing, "fraud-alert source")
    elif card.get("fraud_alert_active") is None:
        add_unique(missing, "fraud alert status")
    if card.get("velocity_blocked") is True:
        findings.append({"priority": 4, "kind": "velocity_block", "result": "blocked"})
    elif card.get("velocity_blocked") is None:
        add_unique(missing, "velocity-block status")

    pending = Decimal("0")
    overdrafts = 0
    bad_dates = False
    cutoff = today - timedelta(days=30) if today else None
    for txn in txns:
        if not isinstance(txn, dict):
            errors.append("each transaction must be an object")
            continue
        value = amount(txn.get("amount"))
        if txn.get("status") == "pending" and value is not None and value < 0:
            pending += -value
        if txn.get("type") == "overdraft_fee":
            day = parse_date(txn.get("date"))
            if today and day is None: bad_dates = True
            elif today and cutoff <= day <= today: overdrafts += 1
    if bad_dates: errors.append("one or more overdraft-fee dates are unparseable")

    balance = amount(account.get("balance"))
    if balance is None: add_unique(missing, "current checking-account balance")
    elif attempted is not None:
        result = "below_attempted_amount" if balance < attempted else "appears_sufficient"
        findings.append({"priority": 5, "kind": "posted_balance", "result": result, "balance": out_money(balance), "attempted_amount": out_money(attempted)})
    if pending:
        findings.append({"priority": 5, "kind": "pending_debits", "result": "present", "total": out_money(pending)})
    if card.get("overdraft_pos_enabled") is None: add_unique(missing, "POS overdraft setting")

    limit, used = amount(card.get("daily_purchase_limit")), amount(card.get("daily_purchase_used"))
    remaining = None
    if limit is None: add_unique(missing, "daily purchase limit")
    elif used is None: add_unique(missing, "daily purchase amount already used")
    else:
        remaining = limit - used
        findings.append({"priority": 6, "kind": "purchase_limit", "result": "calculated", "daily_limit": out_money(limit), "used_today": out_money(used), "remaining": out_money(remaining)})
        if attempted is not None and attempted > remaining:
            findings.append({"priority": 6, "kind": "purchase_limit", "result": "attempt_exceeds_remaining"})

    opened = parse_date(account.get("date_opened"))
    age = (today - opened).days if today and opened else None
    request = data.get("limit_request") if isinstance(data.get("limit_request"), dict) else None
    assessment = None
    if request is not None:
        requested = amount(request.get("new_limit")); blockers = []; unknown = []
        if request.get("limit_type") != "purchase": blockers.append("Only purchase-limit requests are supported.")
        if requested is None: blockers.append("Requested new_limit is missing or non-numeric.")
        if status != "OPEN": blockers.append("Linked checking account is not OPEN.")
        if card_status != "ACTIVE": blockers.append("Debit card is not ACTIVE.")
        if age is None: unknown.append("Account age cannot be determined.")
        elif age < 60: blockers.append("Checking account is less than 60 days old.")
        if today is None or bad_dates: unknown.append("Complete dated history is needed for the overdraft-fee check.")
        elif overdrafts: blockers.append("An overdraft fee exists in the preceding 30 days.")
        if limit is None: unknown.append("Current daily purchase limit is needed.")
        elif requested is not None and requested > limit * Decimal("1.5"): blockers.append("Requested limit exceeds 150% of current limit.")
        if request.get("temporary_increase_in_last_24h") is True: blockers.append("A temporary increase was already granted within 24 hours.")
        elif request.get("temporary_increase_in_last_24h") is None: unknown.append("24-hour temporary-increase history must be confirmed.")
        assessment = {"requested_new_limit": out_money(requested), "maximum_allowed_new_limit": out_money(limit * Decimal("1.5")) if limit is not None else None, "account_age_days": age, "overdraft_fees_in_prior_30_days": overdrafts if today else None, "blockers": blockers, "unknown_requirements": unknown, "eligible_to_request": not blockers and not unknown, "duration": "24 hours"}

    return {"attempted_amount": out_money(attempted), "pending_debit_total": out_money(pending), "overdraft_fees_in_prior_30_days": overdrafts if today else None, "account_age_days": age, "purchase_limit": {"daily_limit": out_money(limit), "used_today": out_money(used), "remaining": out_money(remaining)}, "findings": sorted(findings, key=lambda x: x["priority"]), "temporary_limit_assessment": assessment, "missing_facts": missing, "validation_errors": errors}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict): raise ValueError("top-level JSON value must be an object")
        result = main(payload)
    except Exception as exc:
        result = {"validation_errors": [str(exc)], "missing_facts": [], "findings": []}
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
