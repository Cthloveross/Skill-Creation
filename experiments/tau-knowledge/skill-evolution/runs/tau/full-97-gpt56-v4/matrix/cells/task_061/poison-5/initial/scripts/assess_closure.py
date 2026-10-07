#!/usr/bin/env python3
"""Assess checking-account closure eligibility from supplied account facts.

Input: one JSON object described in SKILL.md. Output: one JSON object. This script
performs no banking action and does not access external systems.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

TIERS = {
    "light blue account": ("entry", 30, Decimal("15.00"), 0),
    "light green account": ("entry", 30, Decimal("15.00"), 0),
    "green fee-free account": ("entry", 30, Decimal("15.00"), 0),
    "blue account": ("mid", 60, Decimal("25.00"), 3),
    "green account": ("mid", 60, Decimal("25.00"), 3),
    "evergreen account": ("premium", 90, Decimal("50.00"), 7),
    "bluest account": ("elite", 180, Decimal("100.00"), 14),
}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be an ISO date string")
    text = value.strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError("date must begin with YYYY-MM-DD") from exc


def money(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("balance must be a decimal amount") from exc
    if not amount.is_finite():
        raise ValueError("balance must be finite")
    return amount.quantize(Decimal("0.01"))


def assess(record):
    required = ["product_name", "account_type", "status", "balance", "date_opened", "closure_date", "pending_transactions"]
    missing = [key for key in required if key not in record]
    if missing:
        return {"eligible_to_close": False, "reasons": ["Missing required field(s): " + ", ".join(missing)]}

    reasons = []
    product = str(record["product_name"]).strip().lower()
    account_type = str(record["account_type"]).strip().lower()
    tier_info = TIERS.get(product)
    if account_type != "checking":
        reasons.append("The selected account is not a checking account.")
    if tier_info is None:
        reasons.append("Unsupported or ambiguous checking product; determine its tier from authoritative details.")
    if str(record["status"]).strip().upper() != "OPEN":
        reasons.append("Account status must be OPEN.")
    if not isinstance(record["pending_transactions"], bool):
        reasons.append("pending_transactions must be an authoritative boolean.")
    elif record["pending_transactions"]:
        reasons.append("All pending transactions must clear before closure.")

    try:
        opened = parse_date(record["date_opened"])
        closing = parse_date(record["closure_date"])
        days_open = (closing - opened).days
        if days_open < 0:
            reasons.append("Closure date cannot precede opening date.")
    except ValueError as exc:
        opened = closing = None
        days_open = None
        reasons.append(str(exc))

    try:
        balance = money(record["balance"])
        if balance < 0:
            reasons.append("Account balance cannot be negative for closure assessment.")
    except ValueError as exc:
        balance = None
        reasons.append(str(exc))

    fee = Decimal("0.00")
    notice_days = None
    tier = None
    early_fee_applies = None
    if tier_info is not None:
        tier, window_days, configured_fee, notice_days = tier_info
        if days_open is not None and days_open >= 0:
            # "Within N days" includes the Nth day after opening.
            early_fee_applies = days_open <= window_days
            if early_fee_applies:
                fee = configured_fee

    if balance is not None and tier_info is not None and early_fee_applies is not None:
        if early_fee_applies and balance < fee:
            reasons.append("Early-closure fee must be covered by this account balance; no alternative payment method is allowed.")
        elif not early_fee_applies and balance != Decimal("0.00"):
            reasons.append("Balance must be $0 when no early-closure fee applies.")

    return {
        "eligible_to_close": not reasons,
        "reasons": reasons,
        "tier": tier,
        "days_open": days_open,
        "early_fee_applies": early_fee_applies,
        "fee": format(fee, ".2f"),
        "notice_days": notice_days,
        "normalized_status": str(record["status"]).strip().upper(),
        "normalized_balance": format(balance, ".2f") if balance is not None else None,
    }


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        result = assess(data)
    except (json.JSONDecodeError, ValueError) as exc:
        result = {"eligible_to_close": False, "reasons": ["Invalid input: " + str(exc)]}
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
