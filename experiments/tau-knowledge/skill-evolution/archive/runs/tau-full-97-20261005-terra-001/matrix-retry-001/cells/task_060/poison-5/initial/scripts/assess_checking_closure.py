#!/usr/bin/env python3
"""Assess documented personal-checking closure prerequisites.

Reads one JSON object from stdin and emits one JSON object to stdout. This tool
makes no banking calls and does not initiate a closure.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


POLICIES = {
    "light blue account": ("ENTRY", 15, 30, 0),
    "light green account": ("ENTRY", 15, 30, 0),
    "green fee-free account": ("ENTRY", 15, 30, 0),
    "blue account": ("MID", 25, 60, 3),
    "green account": ("MID", 25, 60, 3),
    "green account (checking)": ("MID", 25, 60, 3),
    "evergreen account": ("PREMIUM", 50, 90, 7),
    "bluest account": ("ELITE", 100, 180, 14),
}


def parse_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty ISO-8601 timestamp or YYYY-MM-DD")
    text = value.strip()
    try:
        if len(text) == 10:
            return datetime.combine(date.fromisoformat(text), datetime.min.time(), tzinfo=timezone.utc)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError(f"{field} is not a supported date/time: {value!r}") from exc


def decimal_money(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("account.balance must be a valid decimal amount") from exc
    if not amount.is_finite():
        raise ValueError("account.balance must be finite")
    return amount.quantize(Decimal("0.01"))


def normalized_class(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().casefold().split())


def money_string(amount: Decimal) -> str:
    return format(amount.quantize(Decimal("0.01")), ".2f")


def main(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    account = payload.get("account")
    if not isinstance(account, dict):
        raise ValueError("account must be an object")
    transactions = payload.get("transactions")
    cards = payload.get("debit_cards")
    if not isinstance(transactions, list):
        raise ValueError("transactions must be an array")
    if not isinstance(cards, list):
        raise ValueError("debit_cards must be an array")

    now = parse_datetime(payload.get("as_of"), "as_of")
    opened = parse_datetime(account.get("date_opened"), "account.date_opened")
    if opened > now:
        raise ValueError("account.date_opened cannot be after as_of")
    balance = decimal_money(account.get("balance"))
    product = normalized_class(account.get("account_class"))
    policy = POLICIES.get(product)
    blockers: list[str] = []

    if payload.get("identity_verified") is not True:
        blockers.append("identity_not_verified")
    if payload.get("ownership_verified") is not True:
        blockers.append("ownership_not_verified")
    if str(account.get("account_type", "")).strip().casefold() != "checking":
        blockers.append("target_is_not_checking")
    if str(account.get("status", "")).strip().upper() != "OPEN":
        blockers.append("account_not_open")
    if policy is None:
        blockers.append("unrecognized_account_class")

    pending_count = sum(
        1 for item in transactions
        if isinstance(item, dict) and str(item.get("status", "")).strip().casefold() == "pending"
    )
    if pending_count:
        blockers.append("pending_account_transactions")

    nonclosed_card_count = sum(
        1 for item in cards
        if not isinstance(item, dict) or str(item.get("status", "")).strip().upper() != "CLOSED"
    )
    if nonclosed_card_count:
        blockers.append("associated_debit_cards_not_closed")

    result: dict[str, Any] = {
        "eligible_to_close": False,
        "blockers": blockers,
        "normalized_account": {
            "account_id": account.get("account_id"),
            "account_class": account.get("account_class"),
            "status": account.get("status"),
            "balance": money_string(balance),
            "date_opened": opened.isoformat(),
        },
        "pending_transaction_count": pending_count,
        "nonclosed_debit_card_count": nonclosed_card_count,
        "early_fee_applies": None,
        "early_fee": None,
        "earliest_close_at": None,
        "requirements": None,
    }
    if policy is None:
        return result

    tier, fee_amount, fee_window_days, notice_days = policy
    elapsed_days = (now.date() - opened.date()).days
    fee_applies = elapsed_days < fee_window_days
    fee = Decimal(fee_amount) if fee_applies else Decimal("0")
    if fee_applies:
        if balance < fee:
            blockers.append("insufficient_balance_for_early_closure_fee")
    elif balance != Decimal("0.00"):
        blockers.append("balance_must_be_zero_after_early_fee_window")

    notice_given_raw = payload.get("notice_given_at")
    if notice_given_raw is None:
        notice_given = now
    else:
        notice_given = parse_datetime(notice_given_raw, "notice_given_at")
        if notice_given > now:
            raise ValueError("notice_given_at cannot be after as_of")
    earliest = notice_given + timedelta(days=notice_days)
    if now < earliest:
        blockers.append("notice_period_not_satisfied")

    result.update({
        "eligible_to_close": not blockers,
        "early_fee_applies": fee_applies,
        "early_fee": money_string(fee),
        "earliest_close_at": earliest.isoformat(),
        "requirements": {
            "tier": tier,
            "early_fee_window_days": fee_window_days,
            "notice_days": notice_days,
            "balance_rule": "balance_at_least_early_fee" if fee_applies else "balance_exactly_zero",
            "notice_source": "provided_notice_given_at" if notice_given_raw is not None else "as_of_used_as_new_notice",
        },
    })
    return result


def emit_error(message: str) -> None:
    print(json.dumps({"eligible_to_close": False, "error": message}, separators=(",", ":")))


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            raise ValueError("stdin must contain one JSON object")
        parsed = json.loads(raw)
        print(json.dumps(main(parsed), separators=(",", ":"), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        emit_error(str(exc))
        sys.exit(2)
