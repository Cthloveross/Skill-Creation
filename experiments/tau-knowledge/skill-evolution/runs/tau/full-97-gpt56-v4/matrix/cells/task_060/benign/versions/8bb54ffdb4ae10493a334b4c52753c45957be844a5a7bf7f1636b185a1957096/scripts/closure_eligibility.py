#!/usr/bin/env python3
"""Advisory checking-account closure eligibility calculator.

Input (stdin JSON object):
  account_class: product/class string
  date_opened: ISO date/datetime or MM/DD/YYYY
  current_time: ISO datetime/date or a timestamp beginning YYYY-MM-DD
  balance: decimal-compatible number or string
  status: account status string
  pending_transaction_count: non-negative integer
  notice_given_at: optional supported date/datetime

Output (stdout JSON object): recognized policy fields, time calculations, blockers,
and input_errors. This helper does not call banking systems or authorize closure.
"""
import json
import re
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation

POLICIES = {
    "light blue account": ("entry", 15, 30, 0),
    "light green account": ("entry", 15, 30, 0),
    "green fee-free account": ("entry", 15, 30, 0),
    "blue account": ("mid", 25, 60, 3),
    "green account (checking)": ("mid", 25, 60, 3),
    "evergreen account": ("premium", 50, 90, 7),
    "bluest account": ("elite", 100, 180, 14),
}


def parse_dt(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("must be a nonempty date or timestamp string")
    value = value.strip()
    # Strip a trailing timezone label because policy comparisons only need local dates/times.
    value = re.sub(r"\s+[A-Za-z]{2,5}$", "", value)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ValueError("unsupported date format")


def main():
    try:
        raw = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"input_errors": ["invalid JSON: " + str(exc)]}))
        return
    if not isinstance(raw, dict):
        print(json.dumps({"input_errors": ["input must be a JSON object"]}))
        return

    errors, blockers = [], []
    product = str(raw.get("account_class", "")).strip().casefold()
    policy = POLICIES.get(product)
    if policy is None:
        errors.append("unrecognized checking account_class")
        tier = fee = fee_window = notice_days = None
    else:
        tier, fee, fee_window, notice_days = policy

    opened = now = notice_at = None
    try:
        opened = parse_dt(raw.get("date_opened"))
    except ValueError as exc:
        errors.append("date_opened: " + str(exc))
    try:
        now = parse_dt(raw.get("current_time"))
    except ValueError as exc:
        errors.append("current_time: " + str(exc))

    balance = None
    try:
        balance = Decimal(str(raw.get("balance")))
    except (InvalidOperation, ValueError):
        errors.append("balance must be decimal-compatible")

    pending = raw.get("pending_transaction_count")
    if not isinstance(pending, int) or isinstance(pending, bool) or pending < 0:
        errors.append("pending_transaction_count must be a non-negative integer")
    status = str(raw.get("status", "")).strip().upper()

    age_days = None
    fee_applies = None
    if opened and now:
        age_days = (now.date() - opened.date()).days
        if age_days < 0:
            errors.append("date_opened is after current_time")
        elif policy:
            fee_applies = age_days < fee_window

    earliest = None
    if raw.get("notice_given_at") is not None:
        try:
            notice_at = parse_dt(raw.get("notice_given_at"))
            if policy:
                earliest = notice_at + timedelta(days=notice_days)
                if now and now < earliest:
                    blockers.append("required notice period has not elapsed")
        except ValueError as exc:
            errors.append("notice_given_at: " + str(exc))
    elif policy and notice_days > 0:
        blockers.append("notice timestamp is required to establish eligibility")

    if status != "OPEN":
        blockers.append("account status is not OPEN")
    if isinstance(pending, int) and not isinstance(pending, bool) and pending > 0:
        blockers.append("account has pending transactions")
    if balance is not None and fee_applies is not None:
        if fee_applies and balance < Decimal(fee):
            blockers.append("balance is below the applicable early-closure fee")
        if not fee_applies and balance != Decimal("0"):
            blockers.append("balance must be zero when no early-closure fee applies")

    out = {
        "account_class": raw.get("account_class"),
        "tier": tier,
        "account_age_days": age_days,
        "early_closure_fee": fee if fee_applies else 0 if fee_applies is False else None,
        "early_fee_applies": fee_applies,
        "fee_window_days": fee_window,
        "notice_days": notice_days,
        "earliest_closure_time": earliest.isoformat(sep=" ") if earliest else None,
        "account_level_blockers": blockers,
        "input_errors": errors,
        "account_level_eligible": not errors and not blockers,
        "limitations": [
            "Does not verify debit-card closure requirements.",
            "Does not replace authoritative banking tool results or record notice."
        ]
    }
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
