#!/usr/bin/env python3
"""Screen personal account change prerequisites without making bank actions.

Input is one JSON object on stdin:
{
  "as_of": ISO-8601 datetime/date,
  "identity_verified": bool,
  "customer": {"age": int, "checking_closed_for_cause_within_6mo": bool},
  "accounts": [{"id": str, "type": "checking"|"savings", "personal": bool,
                "status": str, "opened_at": ISO date/datetime or null,
                "balance": number|string, "pending_transactions": bool,
                "in_collections": bool}],
  "request": {"open_checking": {"account_class": str, "confirmed": bool},
              "open_savings": {"account_class": str, "confirmed": bool},
              "close_account_id": str|null}
}
All account facts must originate in authoritative bank records. Output lists policy blocks;
it does not authorize or execute any action.
"""
import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

CLOSURE_RULES = {
    "Light Blue Account": (15, 30, 0),
    "Light Green Account": (15, 30, 0),
    "Green Fee-Free Account": (15, 30, 0),
    "Blue Account": (25, 60, 3),
    "Green Account (checking)": (25, 60, 3),
    "Evergreen Account": (50, 90, 7),
    "Bluest Account": (100, 180, 14),
}


def parse_date(value):
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def money(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def block_if(condition, blocks, text):
    if condition:
        blocks.append(text)


def selected_checking(accounts):
    return [a for a in accounts if a.get("personal", True) and a.get("type") == "checking"]


def selected_savings(accounts):
    return [a for a in accounts if a.get("personal", True) and a.get("type") == "savings"]


def main(data):
    accounts = data.get("accounts") or []
    request = data.get("request") or {}
    customer = data.get("customer") or {}
    as_of = parse_date(data.get("as_of"))
    identity = data.get("identity_verified") is True
    global_blocks = []
    block_if(as_of is None, global_blocks, "missing or invalid authoritative current date/time")
    block_if(not identity, global_blocks, "identity verification is not confirmed")

    checking = selected_checking(accounts)
    savings = selected_savings(accounts)

    c_req = request.get("open_checking")
    checking_blocks = []
    if c_req is None:
        checking_result = {"requested": False, "eligible": False, "blocks": []}
    else:
        block_if(not identity, checking_blocks, "identity verification is required")
        block_if(not isinstance(customer.get("age"), int), checking_blocks, "authoritative customer age is required")
        block_if(isinstance(customer.get("age"), int) and customer["age"] < 18, checking_blocks, "customer must be at least 18")
        block_if(len(checking) >= 4, checking_blocks, "customer already has four personal checking accounts")
        block_if(customer.get("checking_closed_for_cause_within_6mo") is not False, checking_blocks, "checking-closure-for-cause status for prior six months is not cleared")
        block_if(not c_req.get("confirmed"), checking_blocks, "exact checking account class is not customer-confirmed")
        cls = c_req.get("account_class")
        block_if(not isinstance(cls, str) or not cls.endswith("Account"), checking_blocks, "checking account class must be the full official name ending in 'Account'")
        checking_result = {"requested": True, "eligible": not checking_blocks, "blocks": checking_blocks}

    s_req = request.get("open_savings")
    savings_blocks = []
    qualified_checking_ids = []
    if s_req is None:
        savings_result = {"requested": False, "eligible": False, "blocks": [], "qualifying_checking_ids": []}
    else:
        block_if(not identity, savings_blocks, "identity verification is required")
        if as_of is None:
            savings_blocks.append("cannot calculate checking tenure without current date")
        for account in checking:
            opened = parse_date(account.get("opened_at"))
            if account.get("status") == "OPEN" and opened and as_of and (as_of - opened).days >= 14:
                qualified_checking_ids.append(account.get("id"))
        block_if(not qualified_checking_ids, savings_blocks, "no active personal checking account with verified tenure of at least 14 days")
        block_if(len(savings) >= 5, savings_blocks, "customer already has five personal savings accounts")
        for account in accounts:
            bal = money(account.get("balance"))
            if account.get("in_collections") is True:
                savings_blocks.append("an account is in collections")
                break
            if bal is None:
                savings_blocks.append("an account balance is missing or invalid")
                break
            if bal < 0:
                savings_blocks.append("an account has a negative balance")
                break
        block_if(not s_req.get("confirmed"), savings_blocks, "exact savings account class is not customer-confirmed")
        cls = s_req.get("account_class")
        block_if(not isinstance(cls, str) or not cls.endswith("Account"), savings_blocks, "savings account class must be the full official name ending in 'Account'")
        savings_result = {"requested": True, "eligible": not savings_blocks, "blocks": savings_blocks, "qualifying_checking_ids": qualified_checking_ids}

    closure_id = request.get("close_account_id")
    closure_blocks = []
    closure = {"requested": bool(closure_id), "eligible": False, "blocks": closure_blocks}
    if closure_id:
        matches = [a for a in accounts if a.get("id") == closure_id]
        if len(matches) != 1:
            closure_blocks.append("target closure account was not uniquely found")
        else:
            account = matches[0]
            closure["account_class"] = account.get("account_class")
            block_if(account.get("type") != "checking", closure_blocks, "this screening supports personal checking closure only")
            block_if(account.get("personal", True) is not True, closure_blocks, "target is not confirmed as a personal account")
            block_if(account.get("status") != "OPEN", closure_blocks, "account status must be OPEN")
            block_if(account.get("pending_transactions") is not False, closure_blocks, "pending transaction state must be confirmed false")
            rule = CLOSURE_RULES.get(account.get("account_class"))
            if rule is None:
                closure_blocks.append("closure tier is unsupported or account class is unrecognized")
            else:
                fee, period, notice = rule
                opened = parse_date(account.get("opened_at"))
                if not opened or not as_of:
                    closure_blocks.append("account opening date and current date are required to calculate early-closure fee")
                else:
                    early = (as_of - opened).days < period
                    closure.update({"early_closure_fee": str(fee if early else 0), "notice_period_days": notice, "early_fee_applies": early})
                    balance = money(account.get("balance"))
                    if balance is None:
                        closure_blocks.append("actual current balance is required")
                    elif early and balance < Decimal(fee):
                        closure_blocks.append("balance is below the applicable early-closure fee")
                    elif not early and balance != Decimal("0"):
                        closure_blocks.append("balance must be exactly zero when no early-closure fee applies")
            closure["eligible"] = not closure_blocks

    return {"global_blocks": global_blocks, "checking_opening": checking_result, "savings_opening": savings_result, "closure": closure,
            "note": "Eligibility is a screening result only. Confirm authority, ownership, product requirements, funds, fees, cutoffs, and explicit customer authorization before an actual banking action."}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": "invalid input", "detail": str(exc)}))
        sys.exit(2)
