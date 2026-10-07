#!/usr/bin/env python3
"""Evaluate documented checking-account closure prerequisites.

Input JSON:
{
  "account": {"account_id": str, "account_type": str, "account_class": str,
              "status": str, "balance"|"current_holdings": number|string,
              "date_opened": ISO date or MM/DD/YYYY},
  "as_of": ISO date or MM/DD/YYYY,
  "transactions": [{"status": str}, ...],
  "cards": [{"status": str}, ...]
}
Output JSON contains eligibility, applicable fee and notice, and explicit blockers.
"""
import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

TIERS = {
    "light blue account": (30, Decimal("15"), 0),
    "light green account": (30, Decimal("15"), 0),
    "green fee-free account": (30, Decimal("15"), 0),
    "blue account": (60, Decimal("25"), 3),
    "green account": (60, Decimal("25"), 3),
    "green account (checking)": (60, Decimal("25"), 3),
    "evergreen account": (90, Decimal("50"), 7),
    "bluest account": (180, Decimal("100"), 14),
}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("date must use YYYY-MM-DD or MM/DD/YYYY")


def money(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("balance/current_holdings must be numeric")


def main(data):
    account = data.get("account")
    if not isinstance(account, dict):
        raise ValueError("account object is required")
    blockers, actions = [], []
    account_type = str(account.get("account_type", "")).strip().lower()
    status = str(account.get("status", "")).strip().upper()
    class_key = str(account.get("account_class", "")).strip().lower()
    tier = TIERS.get(class_key)

    if account_type != "checking":
        blockers.append("Selected account is not a checking account.")
    if status != "OPEN":
        blockers.append("Account status must be OPEN.")
    if tier is None:
        blockers.append("Unsupported or unrecognized account class; determine closure tier manually.")
        window, fee, notice = 0, Decimal("0"), None
    else:
        window, fee, notice = tier

    if "balance" in account:
        balance = money(account["balance"])
    elif "current_holdings" in account:
        balance = money(account["current_holdings"])
    else:
        raise ValueError("account balance or current_holdings is required")

    pending = [t for t in data.get("transactions", []) if str(t.get("status", "")).strip().lower() == "pending"]
    if pending:
        blockers.append("Account has pending transactions.")
        actions.append("Wait for all pending account transactions to settle.")

    early_fee_applies = False
    age_days = None
    if tier is not None:
        opened = parse_date(account.get("date_opened"))
        as_of = parse_date(data.get("as_of"))
        age_days = (as_of - opened).days
        if age_days < 0:
            blockers.append("Account opening date is after the evaluation date.")
        early_fee_applies = 0 <= age_days < window
        if early_fee_applies:
            if balance < fee:
                blockers.append("Balance is insufficient to pay the applicable early-closure fee.")
                actions.append("Maintain at least the early-closure fee in the account before closure.")
        elif balance != Decimal("0"):
            blockers.append("Balance/current holdings must be $0 when no early-closure fee applies.")
            actions.append("Bring the account balance to $0 before closure.")

    open_cards = [c for c in data.get("cards", []) if str(c.get("status", "")).strip().upper() != "CLOSED"]
    if open_cards:
        blockers.append("Associated debit card(s) are not closed.")
        actions.append("Complete required debit-card closure eligibility checks and close linked cards first.")

    return {
        "eligible": not blockers,
        "account_id": account.get("account_id"),
        "account_age_days": age_days,
        "early_fee_applies": early_fee_applies,
        "fee": format(fee if early_fee_applies else Decimal("0"), ".2f"),
        "notice_days": notice,
        "pending_transaction_count": len(pending),
        "nonclosed_card_count": len(open_cards),
        "blockers": blockers,
        "required_actions": actions,
    }

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except (ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"eligible": False, "error": str(exc)}))
        sys.exit(2)
