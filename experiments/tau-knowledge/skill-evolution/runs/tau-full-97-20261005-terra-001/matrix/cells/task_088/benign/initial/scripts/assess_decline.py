#!/usr/bin/env python3
"""Deterministic advisory calculations for debit-card purchase-decline reviews.
Reads one JSON object from stdin and emits one JSON object to stdout.
"""
import json
import sys
from datetime import datetime, date, timedelta
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


def money(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def json_money(value):
    return None if value is None else float(value.quantize(Decimal("0.01")))


def add_missing(missing, item):
    if item not in missing:
        missing.append(item)


def main(payload):
    errors = []
    missing = []
    findings = []
    account = payload.get("account") if isinstance(payload.get("account"), dict) else {}
    card = payload.get("card") if isinstance(payload.get("card"), dict) else {}
    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        errors.append("transactions must be an array")
        transactions = []

    today = parse_date(payload.get("current_time"))
    if today is None:
        errors.append("current_time must be a parseable ISO-like timestamp or date")

    attempted = money(payload.get("attempted_amount"))
    if payload.get("attempted_amount") is not None and attempted is None:
        errors.append("attempted_amount must be numeric")

    account_status = account.get("status")
    card_status = card.get("status")
    if not account_status:
        add_missing(missing, "linked checking account status")
    if not card_status:
        add_missing(missing, "debit card status")

    # Pending debits use the documented sign convention: negative amounts are money out.
    pending_debits = Decimal("0")
    pending_seen = False
    overdraft_count = 0
    malformed_transaction_dates = 0
    cutoff = today - timedelta(days=30) if today else None
    for txn in transactions:
        if not isinstance(txn, dict):
            errors.append("each transaction must be an object")
            continue
        amount = money(txn.get("amount"))
        if txn.get("status") == "pending" and amount is not None and amount < 0:
            pending_debits += -amount
            pending_seen = True
        if txn.get("type") == "overdraft_fee":
            txn_date = parse_date(txn.get("date"))
            if today is None:
                add_missing(missing, "dated overdraft-fee history for the preceding 30 days")
            elif txn_date is None:
                malformed_transaction_dates += 1
            elif cutoff <= txn_date <= today:
                overdraft_count += 1
    if malformed_transaction_dates:
        errors.append("one or more overdraft-fee transaction dates are unparseable")

    if card_status == "FROZEN":
        findings.append({"priority": 1, "kind": "card_status", "result": "frozen", "next_step": "Verify identity and ownership and confirm the linked checking account is OPEN before offering unfreeze."})
    elif card_status == "CLOSED":
        findings.append({"priority": 1, "kind": "card_status", "result": "closed", "next_step": "This card cannot be used or reopened; investigate another active card or replacement options."})
    elif card_status == "PENDING":
        findings.append({"priority": 1, "kind": "card_status", "result": "pending", "next_step": "Confirm activation eligibility and choose the activation tool by issue_reason."})
    elif card_status == "ACTIVE":
        findings.append({"priority": 1, "kind": "card_status", "result": "active", "next_step": "Continue with account, security, balance, and limit checks."})

    if account_status and account_status != "OPEN":
        findings.append({"priority": 2, "kind": "account_status", "result": str(account_status).lower(), "next_step": "Do not transact on the card; follow restricted-account handling where applicable."})
    elif account_status == "OPEN":
        findings.append({"priority": 2, "kind": "account_status", "result": "open", "next_step": "Continue with security checks."})

    fraud_active = card.get("fraud_alert_active")
    fraud_source = card.get("alert_source")
    if fraud_active is True:
        if fraud_source == "bank_initiated":
            findings.append({"priority": 3, "kind": "fraud_alert", "result": "bank_initiated", "next_step": "Do not clear; transfer to the security team."})
        elif fraud_source == "customer_initiated":
            findings.append({"priority": 3, "kind": "fraud_alert", "result": "customer_initiated", "next_step": "May be cleared only after identity verification and confirmation of legitimate activity."})
        else:
            add_missing(missing, "fraud-alert source")
    elif fraud_active is None:
        add_missing(missing, "fraud alert status")

    velocity = card.get("velocity_blocked")
    if velocity is True:
        findings.append({"priority": 4, "kind": "velocity_block", "result": "blocked", "next_step": "It normally expires after 30 minutes; clear early only after verification and a reasonable explanation."})
    elif velocity is None:
        add_missing(missing, "velocity-block status")

    balance = money(account.get("balance"))
    if balance is None:
        add_missing(missing, "current checking-account balance")
    elif attempted is not None:
        if balance < attempted:
            findings.append({"priority": 5, "kind": "posted_balance", "result": "below_attempted_amount", "balance": json_money(balance), "attempted_amount": json_money(attempted), "next_step": "Insufficient posted balance is a likely cause; offer funding or a smaller purchase."})
        else:
            findings.append({"priority": 5, "kind": "posted_balance", "result": "appears_sufficient", "balance": json_money(balance), "attempted_amount": json_money(attempted), "next_step": "Posted balance alone does not establish available funds; review pending activity and authorization holds."})
    if pending_seen:
        findings.append({"priority": 5, "kind": "pending_debits", "result": "present", "total": json_money(pending_debits), "next_step": "Pending debits can reduce available funds."})
    if card.get("overdraft_pos_enabled") is None:
        add_missing(missing, "POS overdraft setting")

    limit = money(card.get("daily_purchase_limit"))
    used = money(card.get("daily_purchase_used"))
    remaining = None
    if limit is None:
        add_missing(missing, "daily purchase limit")
    elif used is None:
        add_missing(missing, "daily purchase amount already used")
    else:
        remaining = limit - used
        findings.append({"priority": 6, "kind": "purchase_limit", "daily_limit": json_money(limit), "used_today": json_money(used), "remaining": json_money(remaining), "result": "calculated", "next_step": "Compare the attempted purchase with remaining daily purchase capacity."})
        if attempted is not None and attempted > remaining:
            findings.append({"priority": 6, "kind": "purchase_limit", "result": "attempt_exceeds_remaining", "attempted_amount": json_money(attempted), "remaining": json_money(remaining), "next_step": "A daily purchase limit is a likely cause."})

    opened = parse_date(account.get("date_opened"))
    account_age_days = (today - opened).days if today and opened else None
    if today and opened is None:
        add_missing(missing, "checking-account opening date")

    request = payload.get("limit_request") if isinstance(payload.get("limit_request"), dict) else None
    assessment = None
    if request is not None:
        requested = money(request.get("new_limit"))
        request_type = request.get("limit_type")
        blockers = []
        unknown = []
        if request_type != "purchase":
            blockers.append("This helper only assesses a purchase-limit request.")
        if requested is None:
            blockers.append("Requested new_limit is missing or non-numeric.")
        if account_status != "OPEN":
            blockers.append("Linked checking account is not OPEN.")
        if card_status != "ACTIVE":
            blockers.append("Debit card is not ACTIVE.")
        if account_age_days is None:
            unknown.append("Account opening date/current date is needed to determine the 60-day requirement.")
        elif account_age_days < 60:
            blockers.append("Checking account is less than 60 days old.")
        if today is None or malformed_transaction_dates:
            unknown.append("Complete, dated transaction history is needed for the 30-day overdraft-fee check.")
        elif overdraft_count > 0:
            blockers.append("An overdraft fee exists in the preceding 30 days.")
        if limit is None:
            unknown.append("Current daily purchase limit is needed for the 150% maximum.")
        elif requested is not None and requested > limit * Decimal("1.5"):
            blockers.append("Requested limit exceeds 150% of the current daily purchase limit.")
        frequency = request.get("temporary_increase_in_last_24h")
        if frequency is True:
            blockers.append("A temporary increase was already granted for this card within 24 hours.")
        elif frequency is None:
            unknown.append("Temporary-increase history for the preceding 24 hours must be confirmed.")
        assessment = {
            "requested_new_limit": json_money(requested),
            "maximum_allowed_new_limit": json_money(limit * Decimal("1.5")) if limit is not None else None,
            "account_age_days": account_age_days,
            "overdraft_fees_in_prior_30_days": overdraft_count if today else None,
            "blockers": blockers,
            "unknown_requirements": unknown,
            "eligible_to_request": not blockers and not unknown,
            "duration": "24 hours"
        }

    return {
        "attempted_amount": json_money(attempted),
        "pending_debit_total": json_money(pending_debits),
        "pending_debits_found": pending_seen,
        "overdraft_fees_in_prior_30_days": overdraft_count if today else None,
        "account_age_days": account_age_days,
        "purchase_limit": {
            "daily_limit": json_money(limit),
            "used_today": json_money(used),
            "remaining": json_money(remaining)
        },
        "findings": sorted(findings, key=lambda item: item["priority"]),
        "temporary_limit_assessment": assessment,
        "missing_facts": missing,
        "validation_errors": errors
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("top-level JSON value must be an object")
        output = main(raw)
    except Exception as exc:
        output = {"validation_errors": [str(exc)], "missing_facts": [], "findings": []}
    print(json.dumps(output, separators=(",", ":"), sort_keys=True))
