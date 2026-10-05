#!/usr/bin/env python3
"""Conservative offline preflight for a coordinated bank-account request.
Reads one JSON object from stdin and emits one JSON object to stdout.
No tool calls, files, or banking actions are performed.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

SAVINGS_TIERS = {
    "Bronze Account": (20, 60, 1, False),
    "Silver Account": (35, 90, 5, False),
    "Silver Plus Account": (35, 90, 5, False),
    "Gold Account": (75, 180, 10, False),
    "Gold Plus Account": (75, 180, 10, False),
    "Gold Years Account": (75, 180, 10, False),
    "Platinum Account": (150, 270, 21, True),
    "Platinum Plus Account": (150, 270, 21, True),
    "Diamond Elite Account": (150, 270, 21, True),
}
CHECKING_TIERS = {
    "Light Blue Account": (15, 30, 0, False),
    "Light Green Account": (15, 30, 0, False),
    "Green Fee-Free Account": (15, 30, 0, False),
    "Blue Account": (25, 60, 3, False),
    "Green Account (checking)": (25, 60, 3, False),
    "Evergreen Account": (50, 90, 7, False),
    "Bluest Account": (100, 180, 14, False),
}


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a date string")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"{field} must use YYYY-MM-DD or MM/DD/YYYY")


def money(value, field):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be numeric")


def open_status(account):
    return str(account.get("status", "")).upper() in {"OPEN", "ACTIVE"}


def account_id(account):
    value = account.get("account_id")
    return value if isinstance(value, str) and value else None


def add_if(condition, target, message):
    if condition:
        target.append(message)


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    today = parse_date(payload.get("as_of"), "as_of")
    accounts = payload.get("accounts", [])
    closures = payload.get("closures", [])
    if not isinstance(accounts, list) or not isinstance(closures, list):
        raise ValueError("accounts and closures must be arrays")

    global_blockers = []
    identity = payload.get("identity_verified") is True
    authority = payload.get("authority_confirmed") is True
    add_if(not identity, global_blockers, "Identity has not been verified.")
    add_if(not authority, global_blockers, "Customer authority and account ownership have not been confirmed.")
    if payload.get("has_collections") is not False:
        global_blockers.append("Collections status is unknown or indicates collections; resolve before personal savings opening.")

    by_id = {}
    parsed_accounts = []
    for index, raw in enumerate(accounts):
        if not isinstance(raw, dict):
            raise ValueError(f"accounts[{index}] must be an object")
        ident = account_id(raw)
        if not ident:
            raise ValueError(f"accounts[{index}].account_id is required")
        if ident in by_id:
            raise ValueError(f"duplicate account_id: {ident}")
        opened = parse_date(raw.get("date_opened"), f"accounts[{index}].date_opened")
        balance = money(raw.get("balance"), f"accounts[{index}].balance")
        item = dict(raw)
        item["_opened"] = opened
        item["_balance"] = balance
        by_id[ident] = item
        parsed_accounts.append(item)

    personal_checking = [a for a in parsed_accounts if a.get("account_type") == "checking" and a.get("customer_role") == "personal"]
    personal_savings = [a for a in parsed_accounts if a.get("account_type") == "savings" and a.get("customer_role") == "personal"]
    business_checking = [a for a in parsed_accounts if a.get("account_type") == "checking" and a.get("customer_role") == "business"]
    negative_balance = any(a["_balance"] < 0 for a in parsed_accounts)

    savings_blockers = list(global_blockers)
    selected_savings = payload.get("selected_savings_class")
    add_if(not isinstance(selected_savings, str) or not selected_savings.endswith("Account"), savings_blockers,
           "Select the exact official personal savings account class ending in 'Account'.")
    eligible_checking = [a for a in personal_checking if open_status(a) and (today - a["_opened"]).days >= 14]
    add_if(not eligible_checking, savings_blockers,
           "An OPEN or ACTIVE personal checking account held for at least 14 days is required.")
    add_if(len(personal_savings) >= 5, savings_blockers,
           "Customer already has five or more personal savings accounts.")
    add_if(negative_balance, savings_blockers,
           "At least one account has a negative balance.")
    if not all(a.get("customer_role") in {"personal", "business"} for a in parsed_accounts):
        savings_blockers.append("Classify each account as personal or business before counting personal savings accounts.")

    business_blockers = list(global_blockers)
    selected_business = payload.get("selected_business_class")
    add_if(not isinstance(selected_business, str) or not selected_business.strip(), business_blockers,
           "Select the exact business checking account class.")
    qualifying_business_source = [a for a in personal_checking if str(a.get("status", "")).upper() == "OPEN" and a["_balance"] >= Decimal("500")]
    add_if(not qualifying_business_source, business_blockers,
           "An OPEN personal checking account with balance at least $500 is required.")
    add_if(len(business_checking) >= 6, business_blockers,
           "Opening another account would exceed the six-business-checking-account limit.")
    add_if(any(str(a.get("status", "")).upper() == "CLOSED" for a in parsed_accounts), business_blockers,
           "Customer has an account with CLOSED status.")

    closure_results = []
    seen_closure_ids = set()
    for index, request in enumerate(closures):
        if not isinstance(request, dict):
            raise ValueError(f"closures[{index}] must be an object")
        ident = request.get("account_id")
        if ident in seen_closure_ids:
            raise ValueError(f"duplicate closure account_id: {ident}")
        seen_closure_ids.add(ident)
        blockers = list(global_blockers)
        account = by_id.get(ident)
        result = {"account_id": ident, "eligible_to_close_now": False, "blockers": blockers,
                  "early_fee": None, "notice_days": None, "early_fee_applies": None,
                  "transferable_excess_before_fee": None}
        if account is None:
            blockers.append("Closure target was not found in the supplied customer accounts.")
            closure_results.append(result)
            continue
        if str(account.get("status", "")).upper() != "OPEN":
            blockers.append("Closure target must have OPEN status.")
        tier = SAVINGS_TIERS.get(account.get("account_class")) if account.get("account_type") == "savings" else CHECKING_TIERS.get(account.get("account_class"))
        if tier is None:
            blockers.append("No documented closure tier was found for this account class; determine fee and notice requirements before closing.")
        else:
            fee, window, notice, manager_required = tier
            age_days = (today - account["_opened"]).days
            early = age_days < window
            result.update({"early_fee": f"{fee:.2f}", "notice_days": notice, "early_fee_applies": early,
                           "transferable_excess_before_fee": f"{max(Decimal('0'), account['_balance'] - Decimal(fee if early else 0)):.2f}"})
            if early and account["_balance"] < Decimal(fee):
                blockers.append(f"Balance is below the applicable early closure fee of ${fee:.2f}.")
            if not early and account["_balance"] != 0:
                blockers.append("No early fee applies, so the account balance must be $0 before closure.")
            if early and account["_balance"] > Decimal(fee):
                blockers.append("Transfer the authorized excess balance while leaving the early closure fee in the account.")
            if manager_required and request.get("manager_approval") is not True:
                blockers.append("Manager approval is required for this elite savings closure.")
            if notice > 0 and request.get("notice_already_satisfied") is not True:
                blockers.append(f"Required closure notice period of {notice} day(s) has not been confirmed as satisfied.")
        if request.get("pending_transactions") is not False:
            blockers.append("Pending transactions are unknown or present for the closure target.")
        if account.get("account_type") == "checking":
            statuses = request.get("linked_card_statuses")
            if not isinstance(statuses, list):
                blockers.append("Linked debit-card statuses must be retrieved before checking closure.")
            elif any(str(status).upper() != "CLOSED" for status in statuses):
                blockers.append("All debit cards linked to this checking account must be closed first.")
        result["eligible_to_close_now"] = not blockers
        closure_results.append(result)

    return {
        "savings_opening": {"eligible": not savings_blockers, "blockers": savings_blockers},
        "business_opening": {"eligible": not business_blockers, "blockers": business_blockers},
        "closures": closure_results,
        "global_blockers": global_blockers,
        "notes": [
            "This is a preflight only; verify every condition with fresh banking-tool data before any action.",
            "Transfer authorizations, source/destination status, sufficient available funds, IDs, limits, and confirmation remain required even when a transferable excess is calculated."
        ]
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), indent=2, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
