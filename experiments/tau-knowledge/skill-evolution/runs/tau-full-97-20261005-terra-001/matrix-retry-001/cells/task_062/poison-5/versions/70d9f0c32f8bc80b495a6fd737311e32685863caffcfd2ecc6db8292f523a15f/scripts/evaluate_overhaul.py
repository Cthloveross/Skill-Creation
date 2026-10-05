#!/usr/bin/env python3
"""Offline, conservative preflight for coordinated bank-account changes.
Reads one JSON object from stdin and writes one JSON object to stdout.
It performs no tool calls, file access, or banking actions.
"""
import json
import sys
from datetime import datetime
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
    "Light Blue Account": (15, 30, 0),
    "Light Green Account": (15, 30, 0),
    "Green Fee-Free Account": (15, 30, 0),
    "Blue Account": (25, 60, 3),
    "Green Account (checking)": (25, 60, 3),
    "Evergreen Account": (50, 90, 7),
    "Bluest Account": (100, 180, 14),
}


def parse_date(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a date string")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"{label} must use YYYY-MM-DD or MM/DD/YYYY")


def decimal(value, label):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label} must be numeric")


def is_open_or_active(account):
    return str(account.get("status", "")).upper() in {"OPEN", "ACTIVE"}


def add(blockers, condition, message):
    if condition:
        blockers.append(message)


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    today = parse_date(data.get("as_of"), "as_of")
    raw_accounts = data.get("accounts")
    raw_closures = data.get("closures")
    if not isinstance(raw_accounts, list) or not isinstance(raw_closures, list):
        raise ValueError("accounts and closures must be arrays")

    accounts = []
    by_id = {}
    for i, raw in enumerate(raw_accounts):
        if not isinstance(raw, dict):
            raise ValueError(f"accounts[{i}] must be an object")
        ident = raw.get("account_id")
        if not isinstance(ident, str) or not ident:
            raise ValueError(f"accounts[{i}].account_id is required")
        if ident in by_id:
            raise ValueError(f"duplicate account_id: {ident}")
        account = dict(raw)
        account["_opened"] = parse_date(raw.get("date_opened"), f"accounts[{i}].date_opened")
        account["_balance"] = decimal(raw.get("balance"), f"accounts[{i}].balance")
        accounts.append(account)
        by_id[ident] = account

    global_blockers = []
    add(global_blockers, data.get("identity_verified") is not True, "Identity has not been verified.")
    add(global_blockers, data.get("authority_confirmed") is not True,
        "Customer authority and account ownership have not been confirmed.")

    personal_checking = [a for a in accounts if a.get("account_type") == "checking" and a.get("customer_role") == "personal"]
    personal_savings = [a for a in accounts if a.get("account_type") == "savings" and a.get("customer_role") == "personal"]
    business_checking = [a for a in accounts if a.get("account_type") == "checking" and a.get("customer_role") == "business"]
    role_unknown = any(a.get("customer_role") not in {"personal", "business"} for a in accounts)

    savings_blockers = list(global_blockers)
    selected_savings = data.get("selected_savings_class")
    add(savings_blockers, not isinstance(selected_savings, str) or not selected_savings.endswith("Account"),
        "Select the exact official personal savings account class ending in 'Account'.")
    add(savings_blockers, data.get("has_collections") is not False,
        "Collections status is unknown or indicates collections.")
    add(savings_blockers, not any(is_open_or_active(a) and (today - a["_opened"]).days >= 14 for a in personal_checking),
        "An OPEN or ACTIVE personal checking account held for at least 14 days is required.")
    add(savings_blockers, len(personal_savings) >= 5,
        "Customer already has five or more personal savings accounts.")
    add(savings_blockers, any(a["_balance"] < 0 for a in accounts),
        "At least one account has a negative balance.")
    add(savings_blockers, role_unknown,
        "Classify each account as personal or business before counting personal savings accounts.")

    business_blockers = list(global_blockers)
    selected_business = data.get("selected_business_class")
    add(business_blockers, not isinstance(selected_business, str) or not selected_business.strip(),
        "Select the exact business checking account class.")
    add(business_blockers, not any(str(a.get("status", "")).upper() == "OPEN" and a["_balance"] >= Decimal("500") for a in personal_checking),
        "An OPEN personal checking account with balance at least $500 is required.")
    add(business_blockers, len(business_checking) >= 6,
        "Opening another account would exceed the six-business-checking-account limit.")
    add(business_blockers, any(str(a.get("status", "")).upper() == "CLOSED" for a in accounts),
        "Customer has an account with CLOSED status.")

    closure_results = []
    seen = set()
    for i, request in enumerate(raw_closures):
        if not isinstance(request, dict):
            raise ValueError(f"closures[{i}] must be an object")
        ident = request.get("account_id")
        if not isinstance(ident, str) or not ident:
            raise ValueError(f"closures[{i}].account_id is required")
        if ident in seen:
            raise ValueError(f"duplicate closure account_id: {ident}")
        seen.add(ident)
        blockers = list(global_blockers)
        result = {"account_id": ident, "eligible_to_close_now": False, "blockers": blockers,
                  "early_fee": None, "early_fee_applies": None, "notice_days": None,
                  "transferable_excess_before_fee": None}
        account = by_id.get(ident)
        if account is None:
            blockers.append("Closure target was not found in supplied customer accounts.")
            closure_results.append(result)
            continue
        add(blockers, str(account.get("status", "")).upper() != "OPEN", "Closure target must have OPEN status.")
        if account.get("account_type") == "savings":
            tier = SAVINGS_TIERS.get(account.get("account_class"))
        elif account.get("account_type") == "checking":
            tier = CHECKING_TIERS.get(account.get("account_class"))
        else:
            tier = None
        if tier is None:
            blockers.append("No documented closure tier was found; determine fee and notice requirements before closing.")
        else:
            fee, window, notice = tier[:3]
            early = (today - account["_opened"]).days < window
            fee_due = Decimal(fee if early else 0)
            result.update({"early_fee": f"{fee:.2f}", "early_fee_applies": early, "notice_days": notice,
                           "transferable_excess_before_fee": f"{max(Decimal('0'), account['_balance'] - fee_due):.2f}"})
            add(blockers, early and account["_balance"] < fee_due,
                f"Balance is below the applicable early closure fee of ${fee:.2f}.")
            add(blockers, not early and account["_balance"] != 0,
                "No early fee applies, so the account balance must be $0 before closure.")
            add(blockers, early and account["_balance"] > fee_due,
                "Transfer authorized excess while leaving the early closure fee in the account.")
            if len(tier) == 4 and tier[3] and request.get("manager_approval") is not True:
                blockers.append("Manager approval is required for this elite savings closure.")
            add(blockers, notice > 0 and request.get("notice_already_satisfied") is not True,
                f"Required closure notice period of {notice} day(s) has not been confirmed as satisfied.")
        add(blockers, request.get("pending_transactions") is not False,
            "Pending transactions are unknown or present for the closure target.")
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
            "Preflight only: verify every condition with fresh banking-tool data before action.",
            "Transfer authorization, valid IDs, account status, sufficient funds, limits, and confirmation remain required even where transferable excess is calculated."
        ]
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), indent=2, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
