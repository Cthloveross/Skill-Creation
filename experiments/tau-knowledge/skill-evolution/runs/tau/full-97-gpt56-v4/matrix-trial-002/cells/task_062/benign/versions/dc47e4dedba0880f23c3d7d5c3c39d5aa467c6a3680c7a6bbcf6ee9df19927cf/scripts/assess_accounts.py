#!/usr/bin/env python3
"""Conservative account-service eligibility assessor.

Input and output are JSON objects on stdin/stdout.  This helper only evaluates a
provided snapshot; it neither calls banking tools nor assumes missing facts.
"""
import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

CLOSURE_RULES = {
    "Light Blue Account": (30, "15", 0, False),
    "Light Green Account": (30, "15", 0, False),
    "Green Fee-Free Account": (30, "15", 0, False),
    "Blue Account": (60, "25", 3, False),
    "Green Account (checking)": (60, "25", 3, False),
    "Evergreen Account": (90, "50", 7, False),
    "Bluest Account": (180, "100", 14, False),
    "Bronze Account": (60, "20", 1, False),
    "Silver Account": (90, "35", 5, False),
    "Silver Plus Account": (90, "35", 5, False),
    "Gold Account": (180, "75", 10, False),
    "Gold Plus Account": (180, "75", 10, False),
    "Gold Years Account": (180, "75", 10, False),
    "Platinum Account": (270, "150", 21, True),
    "Platinum Plus Account": (270, "150", 21, True),
    "Diamond Elite Account": (270, "150", 21, True),
}


def parse_date(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def money(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def account_type(account):
    return str(account.get("account_type", "")).strip().lower()


def is_personal_checking(account):
    # The supplied account snapshot may distinguish ownership explicitly.
    # If it does not, type=checking is the best available normal account datum.
    return account_type(account) == "checking" and account.get("business") is not True


def main(data):
    now = parse_date(data.get("now"))
    accounts = data.get("accounts") if isinstance(data.get("accounts"), list) else []
    identity = data.get("identity_verified") is True
    out = {"business_opening": {}, "personal_savings_opening": {}, "closures": [], "suggested_order": []}

    # Personal savings opening evaluation.
    pblock = []
    pclass = data.get("open_personal_savings_class")
    if not identity:
        pblock.append("identity verification has not been logged")
    if not isinstance(pclass, str) or not pclass.strip().endswith("Account"):
        pblock.append("an exact official personal savings account class ending in 'Account' is required")
    personal_savings = [a for a in accounts if account_type(a) == "savings" and a.get("business") is not True]
    if len(personal_savings) >= 5:
        pblock.append("customer already has five or more personal savings accounts")
    active_checking = [a for a in accounts if is_personal_checking(a) and str(a.get("status", "")).upper() == "OPEN"]
    eligible_checking = False
    if not active_checking:
        pblock.append("no active personal checking account is present")
    for a in active_checking:
        opened = parse_date(a.get("date_opened"))
        if now is None or opened is None:
            continue
        if (now - opened).days >= 14:
            eligible_checking = True
    if active_checking and not eligible_checking:
        pblock.append("an active checking account with at least 14 days tenure has not been confirmed")
    for a in accounts:
        bal = money(a.get("balance"))
        if a.get("collections") is True:
            pblock.append("an account is in collections")
            break
        if bal is not None and bal < 0:
            pblock.append("an account has a negative balance")
            break
        if bal is None:
            pblock.append("one or more account balances are missing or invalid")
            break
    out["personal_savings_opening"] = {"eligible": not pblock, "blockers": pblock}

    # Business checking opening evaluation.
    bblock = []
    bclass = data.get("open_business_checking_class")
    if not identity:
        bblock.append("identity verification has not been logged")
    if not isinstance(bclass, str) or not bclass.strip().endswith("Account"):
        bblock.append("an exact official business checking account class ending in 'Account' is required")
    if any(str(a.get("status", "")).upper() == "CLOSED" for a in accounts):
        bblock.append("customer has an account with CLOSED status")
    qualifying = []
    for a in accounts:
        bal = money(a.get("balance"))
        if is_personal_checking(a) and str(a.get("status", "")).upper() == "OPEN" and bal is not None and bal >= Decimal("500"):
            qualifying.append(a.get("account_id"))
    if not qualifying:
        bblock.append("no OPEN personal checking account with a balance of at least $500 is confirmed")
    business_checking = [a for a in accounts if account_type(a) == "checking" and a.get("business") is True]
    if len(business_checking) + 1 > 6:
        bblock.append("opening would exceed the six business checking account limit")
    out["business_opening"] = {"eligible": not bblock, "blockers": bblock, "qualifying_personal_checking_ids": qualifying}

    # Individual closure evaluation.
    wanted = data.get("close_account_ids") if isinstance(data.get("close_account_ids"), list) else []
    by_id = {str(a.get("account_id")): a for a in accounts if a.get("account_id") is not None}
    for account_id in wanted:
        a = by_id.get(str(account_id))
        blockers = []
        detail = {"account_id": account_id, "eligible": False, "blockers": blockers}
        if not a:
            blockers.append("account was not found in the supplied snapshot")
            out["closures"].append(detail)
            continue
        if str(a.get("status", "")).upper() != "OPEN":
            blockers.append("account status is not OPEN")
        if a.get("pending_transactions") is not False:
            blockers.append("absence of pending transactions is not confirmed")
        rule = CLOSURE_RULES.get(a.get("account_class"))
        if not rule:
            blockers.append("no documented closure tier for this account class")
            out["closures"].append(detail)
            continue
        days, fee_text, notice, approval = rule
        opened = parse_date(a.get("date_opened"))
        bal = money(a.get("balance"))
        if now is None or opened is None:
            blockers.append("current date or account opening date is missing/invalid")
            early = None
        else:
            early = (now - opened).days < days
        if bal is None:
            blockers.append("account balance is missing or invalid")
        elif early is True and bal < Decimal(fee_text):
            blockers.append("balance is below the applicable early-closure fee")
        elif early is False and bal != 0:
            blockers.append("balance must be $0 when no early-closure fee applies")
        if approval and data.get("manager_approval") is not True:
            blockers.append("manager approval is required for this elite savings closure")
        detail.update({"eligible": not blockers, "early_closure": early, "early_fee": fee_text if early else "0", "notice_days": notice})
        out["closures"].append(detail)

    # An open business account must precede closures to preserve the no-CLOSED condition.
    if data.get("open_business_checking_class"):
        out["suggested_order"].append("complete business checking opening first, if eligible and selected")
    if data.get("open_personal_savings_class"):
        out["suggested_order"].append("complete personal savings opening before requested closures if doing so preserves eligibility")
    if wanted:
        out["suggested_order"].append("complete requested closures after any eligible openings")
    return out


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True, default=str))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
