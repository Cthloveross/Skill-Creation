#!/usr/bin/env python3
"""Assess documented personal checking closure conditions from JSON stdin.

This helper is intentionally read-only. It does not call banking tools and does not
make closure decisions beyond reporting whether the supplied facts meet documented
preconditions.
"""

import datetime as dt
import json
import re
import sys
from decimal import Decimal, InvalidOperation

TIERS = {
    "light blue account": ("entry", Decimal("15.00"), 30, 0),
    "light green account": ("entry", Decimal("15.00"), 30, 0),
    "green fee-free account": ("entry", Decimal("15.00"), 30, 0),
    "blue account": ("mid", Decimal("25.00"), 60, 3),
    "green account (checking)": ("mid", Decimal("25.00"), 60, 3),
    "evergreen account": ("premium", Decimal("50.00"), 90, 7),
    "bluest account": ("elite", Decimal("100.00"), 180, 14),
}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    # Timestamps may include a timezone abbreviation unsupported by fromisoformat.
    text = re.sub(r"\s+[A-Za-z]{2,5}$", "", text)
    for parser in (
        lambda: dt.datetime.fromisoformat(text.replace("Z", "+00:00")).date(),
        lambda: dt.datetime.strptime(text, "%m/%d/%Y").date(),
        lambda: dt.datetime.strptime(text, "%Y-%m-%d").date(),
    ):
        try:
            return parser()
        except ValueError:
            pass
    return None


def parse_money(value):
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if isinstance(value, str):
        cleaned = value.strip().replace("$", "").replace(",", "")
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
    return None


def norm(value):
    return str(value or "").strip().casefold()


def main(data):
    account = data.get("account") if isinstance(data.get("account"), dict) else {}
    blockers = []
    account_class = norm(account.get("account_class"))
    rule = TIERS.get(account_class)
    if rule is None:
        blockers.append("Unsupported or unrecognized checking account class.")
        tier = fee = fee_days = notice_days = None
    else:
        tier, fee, fee_days, notice_days = rule

    if norm(account.get("status")) != "open":
        blockers.append("Account status is not OPEN.")
    if norm(account.get("account_type")) not in ("checking", "checkings"):
        blockers.append("Selected account is not identified as a checking account.")

    opened = parse_date(account.get("date_opened"))
    as_of = parse_date(data.get("as_of"))
    age_days = None
    if opened is None or as_of is None:
        blockers.append("Account opening date or assessment time could not be parsed.")
    else:
        age_days = (as_of - opened).days
        if age_days < 0:
            blockers.append("Assessment time precedes the account opening date.")

    transactions = data.get("transactions")
    if not isinstance(transactions, list):
        blockers.append("Account transaction list was not supplied.")
    elif any(norm(t.get("status")) == "pending" for t in transactions if isinstance(t, dict)):
        blockers.append("Account has pending transaction(s).")

    cards = data.get("debit_cards")
    if not isinstance(cards, list):
        blockers.append("Debit-card list was not supplied.")
    elif any(norm(c.get("status")) != "closed" for c in cards if isinstance(c, dict)):
        blockers.append("Associated debit card(s) are not CLOSED.")

    balance = parse_money(account.get("balance"))
    if balance is None:
        blockers.append("Account balance could not be parsed.")

    early_fee_applies = None
    if rule is not None and age_days is not None and age_days >= 0:
        # Treat the stated fee window as inclusive through its final calendar day.
        early_fee_applies = age_days <= fee_days
        if balance is not None:
            if early_fee_applies and balance < fee:
                blockers.append("Balance is below the applicable early-closure fee.")
            if not early_fee_applies and balance != Decimal("0"):
                blockers.append("Balance must be $0 when no early-closure fee applies.")

    result = {
        "account_id": account.get("account_id"),
        "account_class": account.get("account_class"),
        "tier": tier,
        "account_age_days": age_days,
        "early_closure_fee_applies": early_fee_applies,
        "early_closure_fee": (format(fee, ".2f") if fee is not None else None),
        "fee_window_days": fee_days,
        "notice_period_days": notice_days,
        "balance": (format(balance, ".2f") if balance is not None else None),
        "blockers": blockers,
        "eligible_to_submit_closure": not blockers,
    }
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({
            "eligible_to_submit_closure": False,
            "blockers": ["Invalid assessment input: " + str(exc)],
        }, sort_keys=True))
