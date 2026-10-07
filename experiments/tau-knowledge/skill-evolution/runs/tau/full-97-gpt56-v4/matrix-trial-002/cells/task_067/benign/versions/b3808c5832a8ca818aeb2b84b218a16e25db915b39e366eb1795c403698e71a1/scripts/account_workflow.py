#!/usr/bin/env python3
"""Evaluate bank account opening/closure prerequisites from JSON on stdin.

This script performs no bank actions.  It reads the schema documented in SKILL.md
and emits a JSON decision report suitable for a human or tool-using executor.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

ENTRY = {"Light Blue Account", "Light Green Account", "Green Fee-Free Account"}
MID = {"Blue Account", "Green Account (checking)"}
PREMIUM = {"Evergreen Account"}
ELITE = {"Bluest Account"}


def parse_date(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def money(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def tier_for(account_class):
    if account_class in ENTRY:
        return ("entry", Decimal("15"), 30, 0)
    if account_class in MID:
        return ("mid", Decimal("25"), 60, 3)
    if account_class in PREMIUM:
        return ("premium", Decimal("50"), 90, 7)
    if account_class in ELITE:
        return ("elite", Decimal("100"), 180, 14)
    return None


def age_on(dob, today):
    if not dob or not today:
        return None
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def active_checking_with_tenure(accounts, today):
    qualifying = []
    for account in accounts:
        if str(account.get("account_type", "")).lower() != "checking":
            continue
        if str(account.get("status", "")).upper() not in {"ACTIVE", "OPEN"}:
            continue
        opened = parse_date(account.get("date_opened"))
        if opened is not None and today is not None and (today - opened).days >= 14:
            qualifying.append(account.get("account_id"))
    return qualifying


def evaluate_closure(data, accounts, today):
    target_id = data.get("closing_account_id")
    if not target_id:
        return {"evaluated": False, "may_close_now": False, "blocks": ["No closing_account_id was supplied."]}
    account = next((a for a in accounts if a.get("account_id") == target_id), None)
    if account is None:
        return {"evaluated": True, "may_close_now": False, "blocks": ["Closing account was not found in supplied accounts."]}
    result = {
        "evaluated": True,
        "account_id": target_id,
        "account_class": account.get("account_class"),
        "status": account.get("status"),
        "blocks": [],
    }
    if str(account.get("status", "")).upper() != "OPEN":
        result["blocks"].append("Closure requires account status OPEN exactly.")
    if data.get("transactions_retrieved") is not True:
        result["blocks"].append("Transaction history must be retrieved to verify no pending transactions.")
        pending = None
    else:
        transactions = data.get("closing_transactions", [])
        pending = sum(1 for txn in transactions if str(txn.get("status", "")).lower() == "pending")
        if pending:
            result["blocks"].append("Closure is blocked by pending transactions.")
    result["pending_transaction_count"] = pending
    tier = tier_for(account.get("account_class"))
    if tier is None:
        result["blocks"].append("Account class has no documented closure tier in this Skill.")
        result["may_close_now"] = False
        return result
    tier_name, fee, window, notice = tier
    opened = parse_date(account.get("date_opened"))
    if opened is None or today is None:
        result["blocks"].append("A valid account opening date and current date are required.")
        result["may_close_now"] = False
        return result
    days_open = (today - opened).days
    early = days_open < window
    balance = money(account.get("balance", account.get("current_holdings")))
    result.update({"tier": tier_name, "days_open": days_open, "notice_days": notice,
                   "early_closure_fee": str(fee) if early else "0", "early_fee_applies": early})
    if days_open < notice:
        result["blocks"].append("Required notice period has not elapsed.")
    if balance is None:
        result["blocks"].append("A valid account balance is required.")
    elif early and balance < fee:
        result["blocks"].append("Balance is insufficient for the applicable early closure fee.")
    elif not early and balance != Decimal("0"):
        result["blocks"].append("A zero balance is required when no early closure fee applies.")
    result["may_close_now"] = not result["blocks"]
    return result


def compare_savings(options, accounts, held_cards, funds):
    open_checking = {a.get("account_class") for a in accounts
                     if str(a.get("account_type", "")).lower() == "checking"
                     and str(a.get("status", "")).upper() in {"OPEN", "ACTIVE"}}
    output = []
    for opt in options:
        base = money(opt.get("base_apy"))
        opening = money(opt.get("opening_minimum"))
        ongoing = money(opt.get("ongoing_minimum"))
        if base is None or opening is None or ongoing is None:
            output.append({"account_class": opt.get("account_class"), "valid": False,
                           "reason": "base_apy, opening_minimum, and ongoing_minimum must be numeric."})
            continue
        checking_matches = [b for b in opt.get("checking_boosts", [])
                            if b.get("checking_class") in open_checking and money(b.get("apy_bonus")) is not None]
        card_matches = [b for b in opt.get("card_bonuses", [])
                        if b.get("card_class") in held_cards and money(b.get("apy_bonus")) is not None]
        best_checking = max(checking_matches, key=lambda b: money(b["apy_bonus"]), default=None)
        best_card = max(card_matches, key=lambda b: money(b["apy_bonus"]), default=None)
        checking_bonus = money(best_checking["apy_bonus"]) if best_checking else Decimal("0")
        card_bonus = money(best_card["apy_bonus"]) if best_card else Decimal("0")
        output.append({
            "account_class": opt.get("account_class"), "valid": True,
            "base_apy": str(base), "checking_bonus": str(checking_bonus),
            "checking_boost_source": best_checking.get("checking_class") if best_checking else None,
            "card_bonus": str(card_bonus),
            "card_bonus_source": best_card.get("card_class") if best_card else None,
            "effective_documented_apy": str(base + checking_bonus + card_bonus),
            "opening_minimum": str(opening), "ongoing_minimum": str(ongoing),
            "funds_meet_opening_minimum": None if funds is None else funds >= opening,
            "funds_meet_ongoing_minimum": None if funds is None else funds >= ongoing,
        })
    return sorted(output, key=lambda x: Decimal(x.get("effective_documented_apy", "-1")), reverse=True)


def main():
    data = json.load(sys.stdin)
    accounts = data.get("accounts", [])
    today = parse_date(data.get("as_of"))
    blocks = []
    if today is None:
        blocks.append("A valid as_of date/current time is required.")
    customer = data.get("customer", {})
    verified = customer.get("verified") is True
    dob = parse_date(customer.get("date_of_birth"))
    customer_age = age_on(dob, today)
    checking_count = sum(1 for a in accounts if str(a.get("account_type", "")).lower() == "checking")
    savings_count = sum(1 for a in accounts if str(a.get("account_type", "")).lower() == "savings")
    closure_history_known = "checking_closure_for_cause_last_6_months" in data
    checking_blocks = []
    if not verified:
        checking_blocks.append("Customer identity is not verified.")
    if customer_age is None:
        checking_blocks.append("Valid date of birth is required for age eligibility.")
    elif customer_age < 18:
        checking_blocks.append("Customer must be at least 18 for personal checking.")
    if checking_count >= 4:
        checking_blocks.append("Customer already has the maximum four personal checking accounts.")
    if not closure_history_known:
        checking_blocks.append("Checking closure-for-cause history is unknown.")
    elif data["checking_closure_for_cause_last_6_months"] is True:
        checking_blocks.append("A checking account was closed for cause within six months.")
    qualifying_checking = active_checking_with_tenure(accounts, today)
    savings_blocks = []
    if not verified:
        savings_blocks.append("Customer identity is not verified.")
    if not qualifying_checking:
        savings_blocks.append("No ACTIVE or OPEN checking account with at least 14 days tenure was found.")
    if savings_count >= 5:
        savings_blocks.append("Customer already has the maximum five personal savings accounts.")
    if any(a.get("in_collections") is True for a in accounts):
        savings_blocks.append("An account is in collections.")
    for a in accounts:
        balance = money(a.get("balance", a.get("current_holdings")))
        if balance is not None and balance < 0:
            savings_blocks.append("An account has a negative balance.")
            break
    funds = money(data.get("available_savings_funds")) if "available_savings_funds" in data else None
    report = {
        "customer_age": customer_age,
        "checking_opening": {"eligible": not checking_blocks, "existing_checking_count": checking_count, "blocks": checking_blocks},
        "savings_opening": {"eligible": not savings_blocks, "existing_savings_count": savings_count,
                            "qualifying_checking_account_ids": qualifying_checking, "blocks": savings_blocks},
        "closure": evaluate_closure(data, accounts, today),
        "savings_comparisons": compare_savings(data.get("savings_options", []), accounts, set(data.get("held_card_classes", [])), funds),
        "blocks": blocks,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
