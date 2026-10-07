#!/usr/bin/env python3
"""Assess documented checking-account closure prerequisites.

Reads one JSON object from stdin and writes one JSON assessment to stdout.
It performs no I/O other than stdin/stdout and never performs a bank action.
"""

import json
import re
import sys
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation


TIERS = {
    "light blue account": ("ENTRY", Decimal("15.00"), 30, 0),
    "light green account": ("ENTRY", Decimal("15.00"), 30, 0),
    "green fee-free account": ("ENTRY", Decimal("15.00"), 30, 0),
    "blue account": ("MID", Decimal("25.00"), 60, 3),
    "green account (checking)": ("MID", Decimal("25.00"), 60, 3),
    # Some account listings omit the parenthetical for this checking class.
    "green account": ("MID", Decimal("25.00"), 60, 3),
    "evergreen account": ("PREMIUM", Decimal("50.00"), 90, 7),
    "bluest account": ("ELITE", Decimal("100.00"), 180, 14),
}


def parse_time(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp is missing")
    raw = value.strip()
    iso_value = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        return datetime.fromisoformat(iso_value)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S %Z", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    # Supports timestamps such as "2025-11-14 03:40:00 EST" even on
    # platforms where datetime does not recognize the abbreviation.
    match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+[A-Za-z_+/:-]+$", raw)
    if match:
        return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
    raise ValueError("unrecognized timestamp format")


def parse_money(value):
    if isinstance(value, bool):
        raise ValueError("balance is not numeric")
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "").replace("$", "")
        return Decimal(cleaned)
    raise ValueError("balance is missing or not numeric")


def status_of(record):
    value = record.get("status") if isinstance(record, dict) else None
    return value.strip().casefold() if isinstance(value, str) else None


def main(payload):
    errors = []
    blockers = []
    account = payload.get("account")
    transactions = payload.get("transactions", [])
    cards = payload.get("debit_cards", [])

    if not isinstance(account, dict):
        return {"can_close": False, "errors": ["account must be an object"], "blockers": []}
    if not isinstance(transactions, list):
        errors.append("transactions must be an array")
        transactions = []
    if not isinstance(cards, list):
        errors.append("debit_cards must be an array")
        cards = []

    account_class = account.get("account_class")
    normalized_class = account_class.strip().casefold() if isinstance(account_class, str) else ""
    tier = TIERS.get(normalized_class)
    if tier is None:
        errors.append("unrecognized account_class; tier cannot be determined")
        tier_name, fee, fee_days, notice_days = None, None, None, None
    else:
        tier_name, fee, fee_days, notice_days = tier

    try:
        now = parse_time(payload.get("evaluation_time"))
    except ValueError as exc:
        errors.append("evaluation_time: " + str(exc))
        now = None
    try:
        opened = parse_time(account.get("date_opened"))
    except ValueError as exc:
        errors.append("date_opened: " + str(exc))
        opened = None
    try:
        balance = parse_money(account.get("balance"))
    except (ValueError, InvalidOperation) as exc:
        errors.append("balance: " + str(exc))
        balance = None

    account_status = status_of(account)
    if account_status is None:
        errors.append("account status is missing")
    elif account_status != "open":
        blockers.append("account status is not OPEN")

    pending_transaction_count = 0
    for tx in transactions:
        state = status_of(tx)
        if state is None:
            errors.append("a transaction status is missing")
        elif state == "pending":
            pending_transaction_count += 1
    if pending_transaction_count:
        blockers.append("account has pending transactions")

    nonclosed_cards = []
    for card in cards:
        state = status_of(card)
        if state is None:
            errors.append("a debit-card status is missing")
            continue
        if state != "closed":
            if isinstance(card, dict) and card.get("card_id") is not None:
                nonclosed_cards.append(str(card["card_id"]))
            else:
                nonclosed_cards.append("unidentified card")
    if nonclosed_cards:
        blockers.append("linked debit cards are not all CLOSED")

    fee_applies = None
    fee_amount = None
    if tier is not None and now is not None and opened is not None:
        fee_applies = now.date() < (opened.date() + timedelta(days=fee_days))
        fee_amount = fee if fee_applies else Decimal("0.00")
        if balance is not None:
            if fee_applies and balance < fee:
                blockers.append("balance cannot cover the applicable early-closure fee")
            if not fee_applies and balance != Decimal("0"):
                blockers.append("balance must be $0 when no early-closure fee applies")

    notice_deadline = None
    notice_satisfied = None
    if tier is not None:
        if notice_days == 0:
            notice_satisfied = True
        else:
            try:
                notice_given = parse_time(payload.get("notice_given_at"))
                notice_deadline = notice_given + timedelta(days=notice_days)
                if now is not None:
                    notice_satisfied = now >= notice_deadline
                    if not notice_satisfied:
                        blockers.append("required closure notice period has not elapsed")
            except ValueError:
                notice_satisfied = False
                blockers.append("required closure notice timestamp is missing or invalid")

    result = {
        "can_close": not errors and not blockers,
        "errors": errors,
        "blockers": blockers,
        "account_class": account_class,
        "tier": tier_name,
        "fee_applies": fee_applies,
        "fee_amount": format(fee_amount, ".2f") if fee_amount is not None else None,
        "notice_days": notice_days,
        "notice_deadline": notice_deadline.isoformat(sep=" ") if notice_deadline else None,
        "notice_satisfied": notice_satisfied,
        "pending_transaction_count": pending_transaction_count,
        "nonclosed_card_ids": nonclosed_cards,
    }
    return result


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("root JSON value must be an object")
        print(json.dumps(main(incoming), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"can_close": False, "errors": [str(exc)], "blockers": []}, sort_keys=True))
