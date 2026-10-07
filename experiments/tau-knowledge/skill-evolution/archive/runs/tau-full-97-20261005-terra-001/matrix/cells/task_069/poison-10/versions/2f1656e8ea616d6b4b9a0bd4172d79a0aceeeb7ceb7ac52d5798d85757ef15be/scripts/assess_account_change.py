#!/usr/bin/env python3
"""Validate documented personal account opening and closure prerequisites.

Reads one JSON object from stdin and prints one JSON object to stdout.  It makes
no tool calls and intentionally treats missing compliance evidence as a blocker.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

OPEN_STATUSES = {"OPEN", "ACTIVE"}
CLOSURE_TIERS = {
    "Light Blue Account": (15, 30, 0),
    "Light Green Account": (15, 30, 0),
    "Green Fee-Free Account": (15, 30, 0),
    "Blue Account": (25, 60, 3),
    "Green Account (checking)": (25, 60, 3),
    "Evergreen Account": (50, 90, 7),
    "Bluest Account": (100, 180, 14),
}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt).date()
        except ValueError:
            pass
    raise ValueError("unsupported date format: %s" % value)


def money(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("invalid balance: %r" % (value,))


def age_on(dob, today):
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def active(account):
    return str(account.get("status", "")).upper() in OPEN_STATUSES


def personal(account):
    return account.get("personal", True) is not False


def account_type(account):
    return str(account.get("account_type", "")).strip().lower()


def result(eligible, reasons):
    return {"eligible": bool(eligible), "reasons": reasons}


def main(payload):
    errors = []
    try:
        today = parse_date(payload["today"])
    except (KeyError, ValueError) as exc:
        return {"errors": ["today: %s" % exc]}
    try:
        dob = parse_date(payload["date_of_birth"])
        age = age_on(dob, today)
    except (KeyError, ValueError) as exc:
        errors.append("date_of_birth: %s" % exc)
        age = None

    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        return {"errors": errors + ["accounts must be a list"]}

    normalized = []
    for index, account in enumerate(accounts):
        if not isinstance(account, dict):
            errors.append("accounts[%d] must be an object" % index)
            continue
        try:
            row = dict(account)
            row["balance_decimal"] = money(row.get("balance"))
            if active(row):
                row["opened_date"] = parse_date(row.get("date_opened"))
            normalized.append(row)
        except ValueError as exc:
            errors.append("accounts[%d]: %s" % (index, exc))

    verified = payload.get("identity_verified") is True
    authorized = payload.get("authority_confirmed") is True
    personal_checking = [a for a in normalized if personal(a) and account_type(a) == "checking" and active(a)]
    personal_savings = [a for a in normalized if personal(a) and account_type(a) == "savings" and active(a)]

    checking_reasons = []
    if not verified:
        checking_reasons.append("identity has not been verified")
    if not authorized:
        checking_reasons.append("customer authority has not been confirmed")
    if age is None:
        checking_reasons.append("customer age is unavailable")
    elif age < 18:
        checking_reasons.append("customer is younger than 18")
    if len(personal_checking) >= 4:
        checking_reasons.append("opening another checking account would exceed the four-account maximum")
    closed_for_cause = payload.get("closed_for_cause_last_6_months")
    if closed_for_cause is not False:
        if closed_for_cause is True:
            checking_reasons.append("a checking account was closed for cause within six months")
        else:
            checking_reasons.append("closed-for-cause history for the prior six months is not confirmed")
    if errors:
        checking_reasons.append("account data contains validation errors")

    savings_reasons = []
    if not verified:
        savings_reasons.append("identity has not been verified")
    if not authorized:
        savings_reasons.append("customer authority has not been confirmed")
    qualifying_checking = []
    for account in personal_checking:
        opened = account.get("opened_date")
        if opened is not None and (today - opened).days >= 14:
            qualifying_checking.append(account)
    if not qualifying_checking:
        savings_reasons.append("no active personal checking account has been held for at least 14 days")
    if len(personal_savings) >= 5:
        savings_reasons.append("opening another savings account would exceed the five-account maximum")
    collection_accounts = [a.get("account_id") for a in normalized if str(a.get("status", "")).upper() == "COLLECTIONS"]
    if collection_accounts:
        savings_reasons.append("account(s) in collections: %s" % ", ".join(map(str, collection_accounts)))
    negative_accounts = [a.get("account_id") for a in normalized if a["balance_decimal"] < 0]
    if negative_accounts:
        savings_reasons.append("negative balance on account(s): %s" % ", ".join(map(str, negative_accounts)))
    if errors:
        savings_reasons.append("account data contains validation errors")

    closure_reasons = []
    closure_detail = {"eligible": None, "reasons": closure_reasons}
    target_id = payload.get("closure_account_id")
    if target_id is None:
        closure_reasons.append("no closure_account_id supplied")
    else:
        target = next((a for a in normalized if str(a.get("account_id")) == str(target_id)), None)
        if target is None:
            closure_reasons.append("closure account was not found in supplied accounts")
        else:
            closure_detail.update({
                "account_id": target.get("account_id"),
                "account_class": target.get("account_class"),
                "status": target.get("status"),
            })
            if str(target.get("status", "")).upper() != "OPEN":
                closure_reasons.append("closure account status is not OPEN")
            if target.get("pending_transactions") is not False:
                closure_reasons.append("no verified false pending_transactions value for closure account")
            tier = CLOSURE_TIERS.get(target.get("account_class"))
            if tier is None:
                closure_reasons.append("closure tier is not documented for this account class")
            else:
                fee, period, notice = tier
                opened = target.get("opened_date")
                if opened is None:
                    closure_reasons.append("closure account opening date is unavailable")
                else:
                    days_open = (today - opened).days
                    early = days_open < period
                    closure_detail.update({
                        "days_open": days_open,
                        "early_closure_fee": fee if early else 0,
                        "notice_days": notice,
                    })
                    if notice and payload.get("notice_satisfied") is not True:
                        closure_reasons.append("%d-day closure notice is not confirmed" % notice)
                    balance = target["balance_decimal"]
                    if early and balance < Decimal(fee):
                        closure_reasons.append("balance cannot cover the $%d early-closure fee" % fee)
                    if not early and balance != 0:
                        closure_reasons.append("balance must be exactly $0 when no early-closure fee applies")
            if errors:
                closure_reasons.append("account data contains validation errors")
    closure_detail["eligible"] = target_id is not None and not closure_reasons

    return {
        "errors": errors,
        "today": today.isoformat(),
        "customer_age": age,
        "counts": {
            "active_personal_checking": len(personal_checking),
            "active_personal_savings": len(personal_savings),
            "qualifying_checking_held_14_days": len(qualifying_checking),
        },
        "checking_open": result(not checking_reasons, checking_reasons),
        "savings_open": result(not savings_reasons, savings_reasons),
        "closure": closure_detail,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(payload), default=str, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"errors": ["invalid input: %s" % exc]}))
