#!/usr/bin/env python3
"""Evaluate debit-card replacement policy from JSON stdin and emit JSON stdout.

Input schema is documented in SKILL.md. Dates accept ISO-8601 dates/datetimes or
MM/DD/YYYY. This script makes no banking calls and never orders a card.
"""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

COUNTED_REASONS = {"lost", "stolen", "fraud", "damaged"}
TIERS = {
    "ENTRY": {
        "limit": 2, "wait_hours": 48,
        "delivery": {"STANDARD": "0"},
        "design": {"CLASSIC": "0", "PREMIUM": "10", "CUSTOM": "25"},
        "excess": "25",
    },
    "MID": {
        "limit": 3, "wait_hours": 0,
        "delivery": {"STANDARD": "0", "EXPEDITED": "15"},
        "design": {"CLASSIC": "0", "PREMIUM": "10", "CUSTOM": "25"},
        "excess": "15",
    },
    "PREMIUM": {
        "limit": 5, "wait_hours": 0,
        "delivery": {"STANDARD": "0", "EXPEDITED": "0", "RUSH": "35"},
        "design": {"CLASSIC": "0", "PREMIUM": "0", "CUSTOM": "15"},
        "excess": None,
    },
    "ELITE": {
        "limit": None, "wait_hours": 0,
        "delivery": {"STANDARD": "0", "EXPEDITED": "0", "RUSH": "0"},
        "design": {"CLASSIC": "0", "PREMIUM": "0", "CUSTOM": "0"},
        "excess": None,
    },
}
DELIVERY_SPEED = ["STANDARD", "EXPEDITED", "RUSH"]
DESIGN_RANK = ["CLASSIC", "PREMIUM", "CUSTOM"]


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing date")
    value = value.strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError("invalid date: " + value)


def parse_datetime(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing datetime")
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid datetime: " + value) from exc


def one_year_after(day):
    try:
        return day.replace(year=day.year + 1)
    except ValueError:  # Feb 29
        return day.replace(year=day.year + 1, month=2, day=28)


def business_days_elapsed(opened, today):
    if opened >= today:
        return 0
    days = 0
    cursor = opened + timedelta(days=1)
    while cursor <= today:
        if cursor.weekday() < 5:
            days += 1
        cursor += timedelta(days=1)
    return days


def money(value):
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid money value") from exc


def fmt(value):
    return format(value.quantize(Decimal("0.01")), ".2f")


def choose_free(options, ranked):
    free = [item for item in ranked if item in options and money(options[item]) == 0]
    return free[-1] if free else None


def main(payload):
    errors, blocks = [], []
    try:
        now = parse_datetime(payload.get("now"))
    except ValueError as exc:
        return {"order_ready": False, "errors": [str(exc)]}
    today = now.date()
    tier_name = str(payload.get("tier", "")).upper().strip()
    if tier_name not in TIERS:
        return {"order_ready": False, "errors": ["tier must be ENTRY, MID, PREMIUM, or ELITE"]}
    policy = TIERS[tier_name]

    account = payload.get("account") or {}
    verification = payload.get("verification") or {}
    state = payload.get("card_order_state") or {}
    if account.get("account_type") != "checking":
        blocks.append("replacement debit cards can be ordered only for checking accounts")
    if account.get("status") != "OPEN":
        blocks.append("linked checking account is not OPEN")
    try:
        opened = parse_date(account.get("date_opened"))
        elapsed = business_days_elapsed(opened, today)
        if elapsed < 3:
            blocks.append("checking account has not been open for at least 3 business days")
    except ValueError:
        errors.append("account.date_opened is required to validate account tenure")
    for key, label in (("verified", "customer identity"), ("owner_confirmed", "card/account ownership"),
                       ("domestic_address_confirmed", "US domestic delivery address")):
        if verification.get(key) is not True:
            blocks.append(label + " is not confirmed")
    try:
        if int(verification.get("age_years")) < 18:
            blocks.append("customer is under 18")
    except (TypeError, ValueError):
        errors.append("verification.age_years is required")
    try:
        active_after = int(state.get("active_cards_after_close"))
        pending = int(state.get("pending_cards"))
        if active_after > 0:
            blocks.append("an active debit card would remain on the account after closure")
        if pending > 0:
            blocks.append("a pending debit-card order exists")
    except (TypeError, ValueError):
        errors.append("card_order_state active_cards_after_close and pending_cards are required")

    closed_at = None
    if policy["wait_hours"]:
        try:
            closed_at = parse_datetime(state.get("old_card_closed_at"))
            eligible_at = closed_at + timedelta(hours=policy["wait_hours"])
            if now < eligible_at:
                blocks.append("ENTRY replacement waiting period has not elapsed")
        except ValueError:
            errors.append("card_order_state.old_card_closed_at is required for ENTRY waiting period")
    else:
        eligible_at = None

    counted = []
    for card in payload.get("replacement_cards") or []:
        reason = str(card.get("issue_reason", "")).lower().strip()
        if reason not in COUNTED_REASONS:
            continue
        try:
            issued = parse_date(card.get("date_issued"))
        except ValueError:
            errors.append("counted replacement card has missing or invalid date_issued")
            continue
        if issued <= today and issued >= one_year_after(today).replace(year=today.year - 1) if False else False:
            pass
        # A rolling 12-month period begins on the matching calendar date one year ago.
        cutoff = one_year_after(today.replace(year=today.year - 1)) if False else None
        try:
            cutoff = today.replace(year=today.year - 1)
        except ValueError:
            cutoff = today.replace(year=today.year - 1, day=28)
        if cutoff <= issued <= today:
            counted.append(issued)
    counted.sort()
    count = len(counted)

    over_limit = policy["limit"] is not None and count >= policy["limit"]
    excess_fee = Decimal("0")
    age_out_date = one_year_after(counted[0]).isoformat() if counted else None
    if over_limit:
        if policy["excess"] is None:
            blocks.append("replacement limit reached; this tier must wait for the oldest replacement to age out")
        elif payload.get("use_excess_replacement_fee") is True:
            excess_fee = money(policy["excess"])
        else:
            blocks.append("replacement limit reached; customer must choose waiting or authorize the excess replacement fee")

    requested_delivery = payload.get("requested_delivery")
    requested_design = payload.get("requested_design")
    delivery = (str(requested_delivery).upper().strip() if requested_delivery else
                choose_free(policy["delivery"], DELIVERY_SPEED))
    design = (str(requested_design).upper().strip() if requested_design else
              choose_free(policy["design"], DESIGN_RANK))
    if delivery not in policy["delivery"]:
        errors.append("requested delivery is not allowed for account tier")
        delivery_fee = Decimal("0")
    else:
        delivery_fee = money(policy["delivery"][delivery])
    if design not in policy["design"]:
        errors.append("requested design is not allowed for account tier")
        design_fee = Decimal("0")
    else:
        design_fee = money(policy["design"][design])
    total = delivery_fee + design_fee + excess_fee
    try:
        balance = money(account.get("balance"))
        if balance < Decimal("25.00"):
            blocks.append("account balance is below the $25 minimum")
        if balance < total:
            blocks.append("account balance is insufficient for applicable replacement fees")
    except ValueError:
        errors.append("account.balance is required")

    return {
        "order_ready": not errors and not blocks,
        "errors": errors,
        "blocking_reasons": blocks,
        "tier": tier_name,
        "counted_replacements_last_12_months": count,
        "replacement_limit": policy["limit"],
        "limit_age_out_date": age_out_date if over_limit else None,
        "entry_wait_eligible_at": eligible_at.isoformat() if eligible_at else None,
        "allowed_delivery": policy["delivery"],
        "allowed_design": policy["design"],
        "selected_delivery": delivery,
        "selected_design": design,
        "delivery_fee": fmt(delivery_fee),
        "design_fee": fmt(design_fee),
        "excess_replacement_fee": fmt(excess_fee),
        "total_fee": fmt(total),
    }


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(incoming), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"order_ready": False, "errors": [str(exc)]}, separators=(",", ":")))
