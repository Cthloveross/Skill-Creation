#!/usr/bin/env python3
"""Plan a debit-card replacement quote from runtime-supplied facts.

Input and output are JSON objects on stdin/stdout. This program performs no banking
actions and deliberately treats omitted required evidence as a blocker.
"""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

COUNTED_REASONS = {"lost", "stolen", "fraud", "damaged"}
VALID_TIERS = {"ENTRY", "MID", "PREMIUM", "ELITE"}
VALID_DELIVERY = {"STANDARD", "EXPEDITED", "RUSH"}
VALID_DESIGNS = {"BEST_FREE_NONCUSTOM", "CLASSIC", "PREMIUM", "CUSTOM"}


def parse_date(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be YYYY-MM-DD") from exc


def parse_timestamp(value):
    if not isinstance(value, str):
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        raise ValueError("prior_card_closed_at must be an ISO-8601 timestamp")


def business_days_elapsed(opened, today):
    """Count weekdays after opening date through today, excluding weekends."""
    if today <= opened:
        return 0
    cursor = opened + timedelta(days=1)
    count = 0
    while cursor <= today:
        if cursor.weekday() < 5:
            count += 1
        cursor += timedelta(days=1)
    return count


def money_to_cents(value, label):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if amount < 0:
        raise ValueError(f"{label} cannot be negative")
    return int(amount * 100)


def tier_delivery(tier, delivery):
    table = {
        "ENTRY": {"STANDARD": 0},
        "MID": {"STANDARD": 0, "EXPEDITED": 1500},
        "PREMIUM": {"STANDARD": 0, "EXPEDITED": 0, "RUSH": 3500},
        "ELITE": {"STANDARD": 0, "EXPEDITED": 0, "RUSH": 0},
    }
    return table[tier].get(delivery)


def design_choice_and_fee(tier, requested):
    fees = {
        "ENTRY": {"CLASSIC": 0, "PREMIUM": 1000, "CUSTOM": 2500},
        "MID": {"CLASSIC": 0, "PREMIUM": 1000, "CUSTOM": 2500},
        "PREMIUM": {"CLASSIC": 0, "PREMIUM": 0, "CUSTOM": 1500},
        "ELITE": {"CLASSIC": 0, "PREMIUM": 0, "CUSTOM": 0},
    }
    if requested == "BEST_FREE_NONCUSTOM":
        requested = "PREMIUM" if tier in {"PREMIUM", "ELITE"} else "CLASSIC"
    return requested, fees[tier][requested]


def count_replacements(history, today):
    cutoff = today - timedelta(days=365)
    count = 0
    invalid = []
    for idx, record in enumerate(history):
        if not isinstance(record, dict):
            invalid.append(idx)
            continue
        reason = record.get("issue_reason")
        issued = record.get("date_issued")
        if reason not in COUNTED_REASONS:
            continue
        try:
            issue_date = parse_date(issued, f"replacement_history[{idx}].date_issued")
        except ValueError:
            invalid.append(idx)
            continue
        if cutoff <= issue_date <= today:
            count += 1
    return count, invalid


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    today = parse_date(data.get("today"), "today")
    tier = data.get("tier")
    delivery = data.get("requested_delivery")
    design_request = data.get("requested_design", "BEST_FREE_NONCUSTOM")
    if tier not in VALID_TIERS:
        raise ValueError("tier must be ENTRY, MID, PREMIUM, or ELITE")
    if delivery not in VALID_DELIVERY:
        raise ValueError("requested_delivery must be STANDARD, EXPEDITED, or RUSH")
    if design_request not in VALID_DESIGNS:
        raise ValueError("requested_design is invalid")
    history = data.get("replacement_history")
    account = data.get("account")
    if not isinstance(history, list) or not isinstance(account, dict):
        raise ValueError("replacement_history must be an array and account must be an object")

    delivery_fee = tier_delivery(tier, delivery)
    design, design_fee = design_choice_and_fee(tier, design_request)
    blockers = []
    conditions = []
    if delivery_fee is None:
        blockers.append(f"{delivery} delivery is not available for {tier} tier")

    for field in ("account_type", "status", "balance", "date_opened", "has_active_or_pending_card", "customer_age", "domestic_address"):
        if field not in account:
            blockers.append(f"missing account.{field}")
    if not blockers:
        if account["account_type"] != "checking":
            blockers.append("linked account is not a checking account")
        if account["status"] != "OPEN":
            blockers.append("linked checking account is not OPEN")
        balance_cents = money_to_cents(account["balance"], "account.balance")
        if balance_cents < 2500:
            blockers.append("linked account balance is below the $25 minimum")
        opened = parse_date(account["date_opened"], "account.date_opened")
        if business_days_elapsed(opened, today) < 3:
            blockers.append("linked account has not been open for three business days")
        if account["has_active_or_pending_card"] is True:
            blockers.append("account still has an active or pending debit card/order")
        elif account["has_active_or_pending_card"] is not False:
            blockers.append("active/pending-card check is not confirmed")
        if not isinstance(account["customer_age"], int) or account["customer_age"] < 18:
            blockers.append("customer age is not confirmed as at least 18")
        if account["domestic_address"] is not True:
            blockers.append("valid US domestic mailing address is not confirmed")
    else:
        balance_cents = None

    if data.get("pending_refunds_confirmed_clear") is not True:
        blockers.append("pending-refund clearance or written acknowledgement is not confirmed")

    count, invalid_history = count_replacements(history, today)
    if invalid_history:
        blockers.append("replacement history contains invalid counted-card issue dates")

    excess_fee = 0
    if tier == "ENTRY":
        conditions.append("48-hour wait after prior-card closure is required")
        closed_at = parse_timestamp(data.get("prior_card_closed_at"))
        if closed_at is None:
            blockers.append("prior-card closure timestamp is required for ENTRY tier")
        else:
            now_start = datetime.combine(today, datetime.min.time(), tzinfo=closed_at.tzinfo)
            if now_start < closed_at + timedelta(hours=48):
                blockers.append("ENTRY 48-hour post-closure waiting period has not elapsed")
        if count >= 2:
            excess_fee = 2500
            conditions.append("replacement limit reached: customer may wait or explicitly accept $25 excess fee")
    elif tier == "MID":
        if count >= 3:
            excess_fee = 1500
            conditions.append("replacement limit reached: customer may wait or explicitly accept $15 excess fee")
    elif tier == "PREMIUM" and count >= 5:
        blockers.append("PREMIUM replacement limit reached; must wait for oldest replacement to age out")
    elif tier == "ELITE":
        conditions.append("unlimited replacements")

    total_fee = (delivery_fee or 0) + design_fee + excess_fee
    if balance_cents is not None and balance_cents < total_fee:
        blockers.append("available balance is insufficient for disclosed replacement fees")
    if excess_fee:
        conditions.append("excess fee requires explicit acceptance and supported order-tool handling")

    return {
        "eligible_to_order": not blockers,
        "blockers": blockers,
        "replacement_count_last_12_months": count,
        "chosen_delivery": delivery,
        "chosen_design": design,
        "delivery_fee_cents": delivery_fee,
        "design_fee_cents": design_fee,
        "excess_replacement_fee_cents": excess_fee,
        "total_disclosed_fee_cents": total_fee,
        "confirmation_needed_for_nonzero_charge": total_fee > 0,
        "conditions": conditions,
    }


if __name__ == "__main__":
    try:
        result = main(json.load(sys.stdin))
        print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    except (ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
