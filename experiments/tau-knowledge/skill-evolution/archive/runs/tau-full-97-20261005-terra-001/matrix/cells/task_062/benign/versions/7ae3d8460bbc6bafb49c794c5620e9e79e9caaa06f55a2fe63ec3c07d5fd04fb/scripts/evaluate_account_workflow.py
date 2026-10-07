#!/usr/bin/env python3
"""Evaluate documented bank-account opening and closure prerequisites.

Input: one JSON object as described in SKILL.md.
Output: JSON with evidence gaps, blockers, opening eligibility, closure checks, and
an action order. This script performs no banking action.
"""
import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation


def norm(value):
    return str(value or "").strip().upper()


def parse_date(value):
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    prefix = text[:10]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(prefix, fmt).date()
        except ValueError:
            pass
    return None


def money(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def is_open(account):
    return norm(account.get("status")) in {"OPEN", "ACTIVE"}


def is_checking(account):
    return norm(account.get("account_type")) == "CHECKING"


def is_savings(account):
    return norm(account.get("account_type")) == "SAVINGS"


def is_business(account):
    # Runtime records may explicitly classify an account. Do not guess from class names.
    return account.get("is_business") is True or norm(account.get("ownership")) == "BUSINESS"


def main(data):
    now = parse_date(data.get("now"))
    accounts = data.get("accounts") if isinstance(data.get("accounts"), list) else []
    transactions = data.get("transactions_by_account") if isinstance(data.get("transactions_by_account"), dict) else {}
    gaps, blockers = [], []

    if now is None:
        gaps.append("A valid current date/time is required to calculate tenure and early-closure windows.")
    if not data.get("identity_verified", False):
        blockers.append("Identity verification has not been logged.")
    if not accounts:
        gaps.append("No account records were supplied; retrieve all bank accounts before evaluating eligibility.")

    for account in accounts:
        if not account.get("account_id"):
            gaps.append("An account record is missing account_id.")
        if account.get("balance") is None or money(account.get("balance")) is None:
            gaps.append("Account %s has no valid balance." % (account.get("account_id") or "(unknown)"))
        if not account.get("status"):
            gaps.append("Account %s has no status." % (account.get("account_id") or "(unknown)"))

    personal_checkings = []
    unknown_checking_identity = False
    for a in accounts:
        if not is_checking(a):
            continue
        if a.get("is_personal_checking") is True:
            personal_checkings.append(a)
        elif a.get("is_personal_checking") is None and not is_business(a):
            unknown_checking_identity = True

    business_accounts = [a for a in accounts if is_checking(a) and is_business(a)]
    closed = [a for a in accounts if norm(a.get("status")) == "CLOSED"]
    qualifying_personal = [a for a in personal_checkings if norm(a.get("status")) == "OPEN" and (money(a.get("balance")) or Decimal("0")) >= Decimal("500")]

    business_reasons = []
    if not data.get("identity_verified", False):
        business_reasons.append("identity is not verified")
    if not qualifying_personal:
        business_reasons.append("no known personal checking account is OPEN with a balance of at least $500")
    if unknown_checking_identity and not personal_checkings:
        gaps.append("Checking-account records do not establish whether a checking account is personal; this is required for business-checking eligibility.")
    if len(business_accounts) >= 6:
        business_reasons.append("the customer already has 6 business checking accounts")
    if closed:
        business_reasons.append("one or more accounts have status CLOSED")
    bclass = data.get("business_account_class")
    if not isinstance(bclass, str) or not bclass.strip():
        business_reasons.append("no business checking account class was selected")

    personal_savings = [a for a in accounts if is_savings(a) and not is_business(a)]
    active_checkings = [a for a in accounts if is_checking(a) and is_open(a)]
    eligible_tenure = []
    for a in active_checkings:
        opened = parse_date(a.get("date_opened"))
        if opened is None:
            gaps.append("Active checking account %s lacks a valid date_opened." % (a.get("account_id") or "(unknown)"))
        elif now is not None and (now - opened).days >= 14:
            eligible_tenure.append(a)
    negative = [a for a in accounts if money(a.get("balance")) is not None and money(a.get("balance")) < 0]
    collections = [a for a in accounts if norm(a.get("status")) == "COLLECTIONS"]
    savings_reasons = []
    if not data.get("identity_verified", False):
        savings_reasons.append("identity is not verified")
    if not eligible_tenure:
        savings_reasons.append("no active checking account is confirmed to be at least 14 days old")
    if len(personal_savings) >= 5:
        savings_reasons.append("the customer already has 5 or more personal savings accounts")
    if negative:
        savings_reasons.append("one or more accounts have a negative balance")
    if collections:
        savings_reasons.append("one or more accounts are in collections")
    sclass = data.get("personal_savings_account_class")
    if not isinstance(sclass, str) or not sclass.strip():
        savings_reasons.append("no personal savings account class was selected")
    elif not sclass.strip().endswith("Account"):
        savings_reasons.append("personal savings account_class must be the full official name ending in 'Account'")

    closures = []
    requested = data.get("close_account_ids", [])
    if not isinstance(requested, list):
        requested = []
    by_id = {str(a.get("account_id")): a for a in accounts if a.get("account_id") is not None}
    tiers = {
        "BRONZE ACCOUNT": (60, Decimal("20"), 1),
        "EVERGREEN ACCOUNT": (90, Decimal("50"), 7),
    }
    for account_id in requested:
        aid = str(account_id)
        a = by_id.get(aid)
        item = {"account_id": aid, "eligible": False, "reasons": [], "early_fee": None, "notice_days": None}
        if a is None:
            item["reasons"].append("account was not found in supplied account records")
            closures.append(item)
            continue
        if norm(a.get("status")) != "OPEN":
            item["reasons"].append("account status is not OPEN")
        if aid not in transactions:
            item["reasons"].append("transactions have not been retrieved for this closure request")
        else:
            pending = [t for t in (transactions.get(aid) or []) if norm(t.get("status")) == "PENDING"]
            if pending:
                item["reasons"].append("account has pending transactions")
        balance = money(a.get("balance"))
        tier = tiers.get(norm(a.get("account_class")))
        early = False
        if tier is None:
            item["reasons"].append("no supplied closure tier rule exists for this account class")
        else:
            window, fee, notice = tier
            opened = parse_date(a.get("date_opened"))
            if opened is None or now is None:
                item["reasons"].append("opening date/current date is needed to determine early-closure fee")
            else:
                early = (now - opened).days < window
                item["early_fee"] = str(fee) if early else "0"
                item["notice_days"] = notice
                if balance is None:
                    item["reasons"].append("account balance is invalid")
                elif early and balance < fee:
                    item["reasons"].append("balance is insufficient for the applicable early-closure fee")
                elif not early and balance != 0:
                    item["reasons"].append("balance must be $0 when no early-closure fee applies")
        item["eligible"] = not item["reasons"]
        closures.append(item)

    return {
        "evidence_gaps": sorted(set(gaps)),
        "blocking_reasons": sorted(set(blockers)),
        "openings": {
            "business_checking": {"eligible": not business_reasons and not blockers, "reasons": business_reasons},
            "personal_savings": {"eligible": not savings_reasons and not blockers, "reasons": savings_reasons},
        },
        "closures": closures,
        "recommended_order": [
            "verify identity and retrieve accounts/closure transactions",
            "resolve missing selections and transfer authorizations",
            "open eligible business checking before any requested closure",
            "open eligible personal savings while qualifying checking remains active",
            "perform only authorized transfers",
            "close only accounts whose individual closure checks pass",
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
