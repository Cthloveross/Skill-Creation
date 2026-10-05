#!/usr/bin/env python3
"""Evaluate deterministic personal-checking closure prerequisites from JSON."""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

TIERS = {
    "Light Blue Account": ("entry", 15, 30, 0),
    "Light Green Account": ("entry", 15, 30, 0),
    "Green Fee-Free Account": ("entry", 15, 30, 0),
    "Blue Account": ("mid", 25, 60, 3),
    "Green Account (checking)": ("mid", 25, 60, 3),
    "Evergreen Account": ("premium", 50, 90, 7),
    "Bluest Account": ("elite", 100, 180, 14),
}

def parse_date(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    return None

def money(value):
    try:
        return Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return None

def main(data):
    account = data.get("account") or {}
    blockers, unresolved = [], []
    cls = account.get("account_class")
    tier_info = TIERS.get(cls)
    opened = parse_date(account.get("date_opened"))
    today = parse_date(data.get("as_of"))
    balance = money(account.get("balance", account.get("current_holdings")))

    if tier_info is None:
        unresolved.append("Account class is not in the supported personal-checking closure tier table.")
        tier, fee, window, notice_days = None, None, None, None
    else:
        tier, fee, window, notice_days = tier_info
    if str(account.get("status", "")).upper() != "OPEN":
        blockers.append("Account status must be OPEN.")
    if any(str(t.get("status", "")).lower() == "pending" for t in (data.get("transactions") or [])):
        blockers.append("All pending account transactions must settle before closure.")
    if opened is None or today is None:
        unresolved.append("Opening date and current date are required to determine the early-closure window.")
        fee_applies = None
    elif tier_info is None:
        fee_applies = None
    else:
        fee_applies = (today - opened).days < window
    if balance is None:
        unresolved.append("Current account balance/current holdings is required.")
    elif fee_applies is True and balance < Decimal(fee):
        blockers.append("Balance must cover the applicable early-closure fee.")
    elif fee_applies is False and balance != Decimal("0"):
        blockers.append("Balance/current holdings must be $0 when no early-closure fee applies.")

    cards = data.get("cards") or []
    open_cards = [c for c in cards if str(c.get("status", "")).upper() != "CLOSED"]
    if open_cards:
        blockers.append("Associated debit cards must be closed before checking-account closure.")
    if data.get("cards_complete") is False:
        unresolved.append("Debit-card lookup/status information is incomplete.")

    notice_deadline = None
    if notice_days is not None:
        if notice_days == 0:
            notice_deadline = today.isoformat() if today else None
        else:
            given = parse_date(data.get("notice_given_date"))
            if given is None:
                blockers.append("Required closure notice has not been recorded/provided.")
            else:
                notice_deadline = (given + timedelta(days=notice_days)).isoformat()
                if today is not None and today < parse_date(notice_deadline):
                    blockers.append("Required closure notice period has not elapsed.")

    return {
        "tier": tier,
        "fee": str(fee) if fee is not None else None,
        "fee_applies": fee_applies,
        "notice_days": notice_days,
        "notice_deadline": notice_deadline,
        "eligible_now": not blockers and not unresolved,
        "blockers": blockers,
        "unresolved": unresolved,
    }

if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin))))
    except Exception as exc:
        print(json.dumps({"error": "invalid_input", "detail": str(exc)}))
