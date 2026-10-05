"""Assess published personal-account closure prerequisites.

Reads one JSON object from stdin and writes one JSON object to stdout.  This helper
is intentionally read-only: it neither invokes banking tools nor changes records.
"""

import json
import re
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation


TIERS = {
    "light blue account": ("ENTRY", Decimal("15"), 30, 0),
    "light green account": ("ENTRY", Decimal("15"), 30, 0),
    "green fee-free account": ("ENTRY", Decimal("15"), 30, 0),
    "blue account": ("MID", Decimal("25"), 60, 3),
    "green account": ("MID", Decimal("25"), 60, 3),
    "green account (checking)": ("MID", Decimal("25"), 60, 3),
    "evergreen account": ("PREMIUM", Decimal("50"), 90, 7),
    "bluest account": ("ELITE", Decimal("100"), 180, 14),
}


def parse_date(value, field_name):
    if value is None or str(value).strip() == "":
        raise ValueError(field_name + " is required")
    text = str(value).strip()
    # Keep only the calendar date for policy-day arithmetic.
    candidates = ("%Y-%m-%d", "%m/%d/%Y")
    for fmt in candidates:
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError(field_name + " must be YYYY-MM-DD, MM/DD/YYYY, or an ISO timestamp") from exc


def parse_money(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("account balance is required")
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("account balance must be a decimal amount") from exc
    if not amount.is_finite():
        raise ValueError("account balance must be finite")
    return amount


def normalized(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def resolve_tier(account):
    account_class = normalized(account.get("account_class"))
    account_type = normalized(account.get("account_type"))
    # A generic Green Account must be checking to use the documented mid-tier rule.
    if account_class == "green account" and account_type and "checking" not in account_type:
        raise ValueError("Green Account tier is only documented here for checking accounts")
    if account_class in TIERS:
        return TIERS[account_class]
    raise ValueError("unrecognized account class; do not guess a closure tier")


def money_text(value):
    return format(value.quantize(Decimal("0.01")), "f")


def assess(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    account = payload.get("account")
    transactions = payload.get("transactions")
    if not isinstance(account, dict):
        raise ValueError("account must be an object")
    if not isinstance(transactions, list):
        raise ValueError("transactions must be a list")

    as_of = parse_date(payload.get("as_of"), "as_of")
    opened = parse_date(account.get("date_opened"), "account.date_opened")
    if opened > as_of:
        raise ValueError("account.date_opened cannot be after as_of")
    tier, fee, fee_window_days, notice_days = resolve_tier(account)
    balance_source = account.get("balance", account.get("current_holdings"))
    balance = parse_money(balance_source)
    age_days = (as_of - opened).days
    fee_applies = age_days < fee_window_days

    pending_count = 0
    for item in transactions:
        if not isinstance(item, dict):
            raise ValueError("each transaction must be an object")
        if normalized(item.get("status")) == "pending":
            pending_count += 1

    notice_value = payload.get("notice_given_at")
    if notice_days == 0:
        notice_complete = True
        notice_elapsed = None
    elif notice_value is None or str(notice_value).strip() == "":
        notice_complete = False
        notice_elapsed = None
    else:
        notice_date = parse_date(notice_value, "notice_given_at")
        if notice_date > as_of:
            raise ValueError("notice_given_at cannot be after as_of")
        notice_elapsed = (as_of - notice_date).days
        notice_complete = notice_elapsed >= notice_days

    status_open = normalized(account.get("status")) == "open"
    no_pending = pending_count == 0
    balance_ok = balance >= fee if fee_applies else balance == Decimal("0")
    checks = {
        "recognized_tier": True,
        "account_status_open": status_open,
        "no_pending_account_transactions": no_pending,
        "balance_satisfies_fee_or_zero_rule": balance_ok,
        "notice_period_complete": notice_complete,
    }
    account_ready = all(checks.values())
    account_type = normalized(account.get("account_type"))
    account_class = normalized(account.get("account_class"))
    checking = "checking" in account_type or "checking" in account_class

    return {
        "tier": tier,
        "as_of_date": as_of.isoformat(),
        "account_age_days": age_days,
        "early_closure_fee_applies": fee_applies,
        "early_closure_fee": money_text(fee) if fee_applies else "0.00",
        "fee_window_days": fee_window_days,
        "balance": money_text(balance),
        "required_balance_rule": "balance_at_least_fee" if fee_applies else "balance_exactly_zero",
        "notice_days_required": notice_days,
        "notice_days_elapsed": notice_elapsed,
        "notice_period_complete": notice_complete,
        "pending_transaction_count": pending_count,
        "checks": checks,
        "requires_linked_debit_card_clearance": checking,
        "account_ready_except_cards": account_ready,
        "final_closure_allowed_by_this_helper": False,
        "final_closure_note": "This helper never verifies or clears linked debit-card requirements; complete those requirements separately before closing a checking account.",
    }


def main():
    try:
        payload = json.load(sys.stdin)
        result = {"ok": True, "assessment": assess(payload)}
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        result = {"ok": False, "error": str(exc)}
    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
