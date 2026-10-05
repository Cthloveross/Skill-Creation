#!/usr/bin/env python3
"""Advisory eligibility evaluator for personal account opening and closure.
Reads one JSON object from stdin and emits one JSON object to stdout.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def parse_date(value):
    if not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def amount(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def main(data):
    operation = data.get("operation")
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    accounts = data.get("accounts") if isinstance(data.get("accounts"), list) else []
    blockers, checked = [], []

    today = parse_date(data.get("today"))
    if today is None:
        blockers.append("A valid today date (YYYY-MM-DD or MM/DD/YYYY) is required.")
    else:
        checked.append("current date")

    def active_checking():
        return [a for a in accounts if isinstance(a, dict) and a.get("account_type") == "checking" and a.get("status") == "OPEN"]

    def savings():
        return [a for a in accounts if isinstance(a, dict) and a.get("account_type") == "savings"]

    if operation in ("checking_open", "savings_open"):
        if customer.get("verified") is not True:
            blockers.append("Customer identity verification is required.")
        checked.append("identity verification")

    if operation == "checking_open":
        age = customer.get("age")
        if not isinstance(age, (int, float)) or age < 18:
            blockers.append("Customer must be at least 18 years old.")
        checked.append("age >= 18")
        checking_count = sum(1 for a in accounts if isinstance(a, dict) and a.get("account_type") == "checking")
        if checking_count >= 5:
            blockers.append("Customer already has the maximum of 5 personal checking accounts.")
        checked.append("checking account count")
        if customer.get("closed_checking_for_cause_within_6_months") is not False:
            blockers.append("Checking-closure-for-cause history in the past 6 months must be confirmed absent.")
        checked.append("closure-for-cause history")

    elif operation == "savings_open":
        active = active_checking()
        if not active:
            blockers.append("At least one active checking account is required.")
        checked.append("active checking account")
        if len(savings()) >= 5:
            blockers.append("Customer already has 5 or more personal savings accounts.")
        checked.append("savings account count")
        for account in accounts:
            if not isinstance(account, dict):
                continue
            bal = amount(account.get("balance", account.get("current_holdings")))
            if account.get("in_collections") is True:
                blockers.append("No account may be in collections.")
                break
            if bal is None:
                blockers.append("Every account balance must be available to check for negative balances.")
                break
            if bal < 0:
                blockers.append("Customer has an account with a negative balance.")
                break
        checked.append("collections and negative balances")
        if active and today:
            qualifying = False
            unknown_date = False
            for account in active:
                opened = parse_date(account.get("date_opened"))
                if opened is None:
                    unknown_date = True
                elif (today - opened).days >= 14:
                    qualifying = True
            if not qualifying:
                blockers.append("An active checking account held for at least 14 days is required." if not unknown_date else "Active checking tenure cannot be confirmed from the supplied opening dates.")
        checked.append("checking tenure >= 14 days")

    elif operation == "checking_close":
        target_id = data.get("target_account_id")
        target = next((a for a in accounts if isinstance(a, dict) and a.get("account_id") == target_id), None)
        if target is None or target.get("account_type") != "checking":
            blockers.append("A target checking account must be identified.")
            return result(operation, blockers, checked, {})
        if target.get("status") != "OPEN":
            blockers.append("Target account status must be OPEN.")
        checked.append("target status")
        pending_ids = data.get("pending_transaction_account_ids")
        if not isinstance(pending_ids, list):
            blockers.append("Pending-transaction status must be supplied from transaction history.")
        elif target_id in pending_ids:
            blockers.append("Target account has pending transactions.")
        checked.append("pending transactions")
        bal = amount(target.get("balance", target.get("current_holdings")))
        if bal is None:
            blockers.append("Target account balance is required.")
        account_class = target.get("account_class")
        opened = parse_date(target.get("date_opened"))
        entry = {"Light Blue Account", "Light Green Account", "Green Fee-Free Account"}
        fee = Decimal("0")
        if account_class in entry:
            if today is None or opened is None:
                blockers.append("Target opening date is required to determine the early-closure fee.")
            elif (today - opened).days < 30:
                fee = Decimal("15")
        else:
            blockers.append("Closure tier and terms must be determined from approved account-class rules.")
        if bal is not None:
            if fee > 0 and bal < fee:
                blockers.append("Target balance is insufficient for the applicable early-closure fee.")
            elif fee == 0 and bal != 0:
                blockers.append("Target balance must be exactly $0 when no early-closure fee applies.")
        checked.extend(["closure tier", "early-closure fee", "target balance"])
    else:
        blockers.append("operation must be checking_open, savings_open, or checking_close.")

    facts = {
        "checking_count": sum(1 for a in accounts if isinstance(a, dict) and a.get("account_type") == "checking"),
        "savings_count": len(savings()),
        "active_checking_count": len(active_checking()),
    }
    return result(operation, blockers, checked, facts)


def result(operation, blockers, checked, facts):
    return {
        "operation": operation,
        "eligible": not blockers,
        "blockers": blockers,
        "facts": facts,
        "requirements_checked": checked,
        "advisory": "This result does not replace identity, authority, ownership, card, transfer, or tool-result verification."
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"eligible": False, "blockers": ["Invalid evaluator input: " + str(exc)]}))
