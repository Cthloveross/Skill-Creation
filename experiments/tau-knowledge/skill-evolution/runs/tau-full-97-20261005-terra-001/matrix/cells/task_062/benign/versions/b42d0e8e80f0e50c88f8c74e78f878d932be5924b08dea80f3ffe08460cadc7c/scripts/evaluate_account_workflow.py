#!/usr/bin/env python3
"""Evaluate documented account-opening and closure prerequisites without taking action.

Input: one JSON object described in SKILL.md.
Output: one JSON object containing evidence gaps, opening eligibility, closure checks,
and safe sequencing guidance. No tools are called and no bank state is changed.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation


def text(value):
    return str(value or "").strip()


def upper(value):
    return text(value).upper()


def parse_date(value):
    value = text(value)
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value[:10], fmt).date()
        except ValueError:
            continue
    return None


def parse_money(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def account_type(account):
    return upper(account.get("account_type"))


def is_open(account):
    return upper(account.get("status")) in {"OPEN", "ACTIVE"}


def is_business(account):
    return account.get("is_business") is True or upper(account.get("ownership")) == "BUSINESS"


def is_personal_checking(account):
    if account_type(account) != "CHECKING":
        return False
    # Explicit false is authoritative. If business status is explicitly known, honor it.
    if account.get("is_personal_checking") is not None:
        return account.get("is_personal_checking") is True
    return not is_business(account)


def append_once(items, message):
    if message not in items:
        items.append(message)


def main(data):
    accounts = data.get("accounts") if isinstance(data.get("accounts"), list) else []
    tx_by_account = data.get("transactions_by_account")
    tx_by_account = tx_by_account if isinstance(tx_by_account, dict) else {}
    now = parse_date(data.get("now"))
    verified = data.get("identity_verified") is True
    gaps = []

    if not accounts:
        gaps.append("No account records were supplied; retrieve all customer bank accounts.")
    if now is None:
        gaps.append("A valid current date is required for tenure and early-closure calculations.")

    for account in accounts:
        aid = text(account.get("account_id")) or "(unknown)"
        if not text(account.get("account_id")):
            append_once(gaps, "An account record is missing account_id.")
        if not text(account.get("status")):
            append_once(gaps, "Account %s is missing status." % aid)
        if parse_money(account.get("balance")) is None:
            append_once(gaps, "Account %s has no valid balance." % aid)

    personal_checkings = [a for a in accounts if is_personal_checking(a)]
    eligible_personal = [
        a for a in personal_checkings
        if upper(a.get("status")) == "OPEN"
        and parse_money(a.get("balance")) is not None
        and parse_money(a.get("balance")) >= Decimal("500")
    ]
    business_accounts = [a for a in accounts if account_type(a) == "CHECKING" and is_business(a)]
    closed_accounts = [a for a in accounts if upper(a.get("status")) == "CLOSED"]

    business_reasons = []
    if not verified:
        business_reasons.append("identity verification has not been logged")
    if not eligible_personal:
        business_reasons.append("no personal checking account is confirmed OPEN with a balance of at least $500")
    if len(business_accounts) >= 6:
        business_reasons.append("the customer already has 6 business checking accounts")
    if closed_accounts:
        business_reasons.append("one or more accounts have status CLOSED")
    if not text(data.get("business_account_class")):
        business_reasons.append("no business checking account class was selected")

    savings_accounts = [a for a in accounts if account_type(a) == "SAVINGS" and not is_business(a)]
    active_checkings = [a for a in accounts if account_type(a) == "CHECKING" and is_open(a)]
    tenure_checkings = []
    for account in active_checkings:
        opened = parse_date(account.get("date_opened"))
        if opened is None:
            append_once(gaps, "Active checking account %s lacks a valid date_opened." % (text(account.get("account_id")) or "(unknown)"))
        elif now is not None and (now - opened).days >= 14:
            tenure_checkings.append(account)

    negative = [a for a in accounts if parse_money(a.get("balance")) is not None and parse_money(a.get("balance")) < 0]
    collections = [a for a in accounts if upper(a.get("status")) == "COLLECTIONS"]
    savings_class = text(data.get("personal_savings_account_class"))
    savings_reasons = []
    if not verified:
        savings_reasons.append("identity verification has not been logged")
    if not tenure_checkings:
        savings_reasons.append("no active checking account is confirmed to be at least 14 days old")
    if len(savings_accounts) >= 5:
        savings_reasons.append("the customer already has 5 or more personal savings accounts")
    if negative:
        savings_reasons.append("one or more accounts have a negative balance")
    if collections:
        savings_reasons.append("one or more accounts are in collections")
    if not savings_class:
        savings_reasons.append("no personal savings account class was selected")
    elif not savings_class.endswith("Account"):
        savings_reasons.append("personal savings account_class must be the full official name ending in 'Account'")

    by_id = {text(a.get("account_id")): a for a in accounts if text(a.get("account_id"))}
    requested = data.get("close_account_ids") if isinstance(data.get("close_account_ids"), list) else []
    closure_rules = {
        "BRONZE ACCOUNT": (60, Decimal("20"), 1),
        "EVERGREEN ACCOUNT": (90, Decimal("50"), 7),
    }
    closures = []
    for requested_id in requested:
        aid = text(requested_id)
        account = by_id.get(aid)
        item = {
            "account_id": aid,
            "eligible_to_close_now": False,
            "reasons": [],
            "early_closure_fee": None,
            "notice_days": None,
            "requires_balance_disposition": False,
        }
        if account is None:
            item["reasons"].append("account was not found in supplied records")
            closures.append(item)
            continue
        if upper(account.get("status")) != "OPEN":
            item["reasons"].append("account status is not OPEN")
        if aid not in tx_by_account:
            item["reasons"].append("transaction history has not been retrieved")
        else:
            records = tx_by_account.get(aid) or []
            if any(isinstance(tx, dict) and upper(tx.get("status")) == "PENDING" for tx in records):
                item["reasons"].append("account has pending transactions")

        balance = parse_money(account.get("balance"))
        if balance is None:
            item["reasons"].append("account balance is invalid")
        elif balance != 0:
            item["requires_balance_disposition"] = True
            item["reasons"].append("nonzero balance needs an explicitly authorized disposition before closure")

        rule = closure_rules.get(upper(account.get("account_class")))
        if rule is None:
            item["reasons"].append("no supplied closure tier rule exists for this account class")
        else:
            window, fee, notice = rule
            opened = parse_date(account.get("date_opened"))
            if opened is None or now is None:
                item["reasons"].append("opening date and current date are needed to determine early-closure terms")
            else:
                early = (now - opened).days < window
                item["early_closure_fee"] = str(fee if early else Decimal("0"))
                item["notice_days"] = notice
                if early and balance is not None and balance < fee:
                    item["reasons"].append("balance is insufficient for the applicable early-closure fee")
        item["eligible_to_close_now"] = not item["reasons"]
        closures.append(item)

    return {
        "evidence_gaps": sorted(set(gaps)),
        "openings": {
            "business_checking": {"eligible": not business_reasons, "reasons": business_reasons},
            "personal_savings": {"eligible": not savings_reasons, "reasons": savings_reasons},
        },
        "closures": closures,
        "recommended_order": [
            "verify identity and retrieve current accounts and closure transactions",
            "resolve only missing selections, savings funding choices, and closure-balance authorizations",
            "open eligible business checking before any closure",
            "open eligible personal savings while qualifying checking remains active",
            "perform only explicitly authorized transfers",
            "close only accounts that pass every individual closure check",
        ],
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), indent=2, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
