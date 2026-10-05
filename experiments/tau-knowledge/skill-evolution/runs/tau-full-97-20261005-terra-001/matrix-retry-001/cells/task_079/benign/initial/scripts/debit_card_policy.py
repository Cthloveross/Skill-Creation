#!/usr/bin/env python3
"""Deterministic policy helpers for stolen debit-card workflows.

Reads one JSON object from stdin and emits one JSON object to stdout.

Actions:
  closure_check:
    {"action":"closure_check", "card":{"user_id":str,"status":str,
     "date_issued":date}, "request_user_id":str, "verified":bool,
     "reason":str, "now":date, "pending_card_transactions":bool,
     "pending_refunds":bool, "refund_acknowledged":bool}

  replacement_quote:
    {"action":"replacement_quote", "tier":str OR "account_class":str,
     "now":date, "cards":[{"issue_reason":str,"date_issued":date}],
     "delivery":str|null, "design":str|null,
     "accept_excess_fee":bool}

  order_precheck:
    {"action":"order_precheck", "account":{"account_type":str,
     "status":str,"date_opened":date,"balance":number}, "now":date,
     "verified":bool, "us_address_confirmed":bool,
     "has_active_card":bool, "has_pending_card":bool}

Dates may be YYYY-MM-DD, an ISO timestamp, or MM/DD/YYYY. Output contains
allowed/eligible booleans, machine-readable blockers, fees in USD, and details.
This program never performs bank actions and intentionally blocks unknown or
malformed required facts.
"""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

VALID_REASONS = {"lost", "stolen", "fraud_suspected", "damaged", "no_longer_needed", "account_closing"}
SECURITY_REASONS = {"lost", "stolen", "fraud_suspected"}
REPLACEMENT_REASONS = {"lost", "stolen", "fraud", "damaged"}
CLASS_TIERS = {
    "LIGHT BLUE ACCOUNT": "ENTRY",
    "LIGHT GREEN ACCOUNT": "ENTRY",
    "GREEN FEE-FREE ACCOUNT": "ENTRY",
    "BLUE ACCOUNT": "MID",
    "GREEN ACCOUNT (CHECKING)": "MID",
    "EVERGREEN ACCOUNT": "PREMIUM",
    "BLUEST ACCOUNT": "ELITE",
}
POLICY = {
    "ENTRY": {"limit": 2, "wait_hours": 48,
              "delivery": {"STANDARD": Decimal("0")},
              "design": {"CLASSIC": Decimal("0"), "PREMIUM": Decimal("10"), "CUSTOM": Decimal("25")},
              "excess_fee": Decimal("25"), "can_pay_excess": True},
    "MID": {"limit": 3, "wait_hours": 0,
            "delivery": {"STANDARD": Decimal("0"), "EXPEDITED": Decimal("15")},
            "design": {"CLASSIC": Decimal("0"), "PREMIUM": Decimal("10"), "CUSTOM": Decimal("25")},
            "excess_fee": Decimal("15"), "can_pay_excess": True},
    "PREMIUM": {"limit": 5, "wait_hours": 0,
                "delivery": {"STANDARD": Decimal("0"), "EXPEDITED": Decimal("0"), "RUSH": Decimal("35")},
                "design": {"CLASSIC": Decimal("0"), "PREMIUM": Decimal("0"), "CUSTOM": Decimal("15")},
                "excess_fee": None, "can_pay_excess": False},
    "ELITE": {"limit": None, "wait_hours": 0,
              "delivery": {"STANDARD": Decimal("0"), "EXPEDITED": Decimal("0"), "RUSH": Decimal("0")},
              "design": {"CLASSIC": Decimal("0"), "PREMIUM": Decimal("0"), "CUSTOM": Decimal("0")},
              "excess_fee": None, "can_pay_excess": False},
}


def parse_day(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value[:10] if fmt == "%Y-%m-%d" else value, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def money(value):
    return format(value.quantize(Decimal("0.01")), ".2f")


def as_bool(value):
    return value is True


def tier_for(payload):
    tier = payload.get("tier")
    if isinstance(tier, str) and tier.strip().upper() in POLICY:
        return tier.strip().upper()
    account_class = payload.get("account_class")
    if isinstance(account_class, str):
        return CLASS_TIERS.get(account_class.strip().upper())
    return None


def one_year_before(today):
    try:
        return today.replace(year=today.year - 1)
    except ValueError:  # Feb 29
        return today.replace(year=today.year - 1, month=2, day=28)


def closure_check(p):
    card = p.get("card") if isinstance(p.get("card"), dict) else {}
    now = parse_day(p.get("now"))
    reason = str(p.get("reason", "")).lower()
    blockers = []
    details = {}
    if not as_bool(p.get("verified")):
        blockers.append("customer_not_verified")
    if not p.get("request_user_id") or card.get("user_id") != p.get("request_user_id"):
        blockers.append("card_owner_mismatch")
    if str(card.get("status", "")).upper() not in {"ACTIVE", "PENDING"}:
        blockers.append("card_status_not_active_or_pending")
    if reason not in VALID_REASONS:
        blockers.append("invalid_closure_reason")
    if p.get("pending_card_transactions") is not False:
        blockers.append("pending_or_unknown_card_transactions")
    if p.get("pending_refunds") is not False and not as_bool(p.get("refund_acknowledged")):
        blockers.append("pending_or_unknown_refunds_without_written_acknowledgement")
    issued = parse_day(card.get("date_issued"))
    if reason not in SECURITY_REASONS:
        if not now or not issued:
            blockers.append("card_age_unknown")
        else:
            earliest = issued + timedelta(days=14)
            details["earliest_eligible_closure_date"] = earliest.isoformat()
            if now < earliest:
                blockers.append("minimum_card_age_not_met")
    else:
        details["minimum_card_age_bypassed"] = True
    return {"allowed": not blockers, "blockers": blockers, "details": details}


def replacement_quote(p):
    tier = tier_for(p)
    now = parse_day(p.get("now"))
    if not tier or not now:
        return {"eligible": False, "blockers": ["unknown_tier_or_current_date"], "details": {}}
    policy = POLICY[tier]
    cutoff = one_year_before(now)
    counted = []
    unknown_history_dates = False
    cards = p.get("cards") if isinstance(p.get("cards"), list) else []
    for card in cards:
        if not isinstance(card, dict):
            continue
        if str(card.get("issue_reason", "")).lower() in REPLACEMENT_REASONS:
            issued = parse_day(card.get("date_issued"))
            if issued is None:
                unknown_history_dates = True
            elif cutoff <= issued <= now:
                counted.append(issued)
    blockers = []
    needs_customer_choice = []
    if unknown_history_dates:
        blockers.append("replacement_history_date_unknown")
    at_limit = policy["limit"] is not None and len(counted) >= policy["limit"]
    excess_fee = Decimal("0")
    if at_limit:
        if policy["can_pay_excess"]:
            if as_bool(p.get("accept_excess_fee")):
                excess_fee = policy["excess_fee"]
            else:
                needs_customer_choice.append("wait_until_oldest_replacement_ages_out_or_accept_excess_fee")
        else:
            blockers.append("replacement_limit_reached_must_wait")
    delivery = p.get("delivery")
    delivery = delivery.strip().upper() if isinstance(delivery, str) else None
    design = p.get("design")
    design = design.strip().upper() if isinstance(design, str) else None
    if not delivery:
        needs_customer_choice.append("delivery")
        delivery_fee = None
    elif delivery not in policy["delivery"]:
        blockers.append("delivery_not_available_for_tier")
        delivery_fee = None
    else:
        delivery_fee = policy["delivery"][delivery]
    if not design:
        needs_customer_choice.append("design")
        design_fee = None
    elif design not in policy["design"]:
        blockers.append("invalid_design")
        design_fee = None
    else:
        design_fee = policy["design"][design]
    eligible = not blockers and not needs_customer_choice
    result = {
        "eligible": eligible,
        "tier": tier,
        "blockers": blockers,
        "needs_customer_choice": needs_customer_choice,
        "replacement_count_last_12_months": len(counted),
        "replacement_limit": policy["limit"],
        "wait_after_closure_hours": policy["wait_hours"],
        "delivery": delivery,
        "design": design,
        "delivery_fee": money(delivery_fee) if delivery_fee is not None else None,
        "design_fee": money(design_fee) if design_fee is not None else None,
        "excess_replacement_fee": money(excess_fee),
    }
    if delivery_fee is not None and design_fee is not None:
        result["total_known_fee"] = money(delivery_fee + design_fee + excess_fee)
    if counted:
        result["oldest_counted_replacement_date"] = min(counted).isoformat()
        result["oldest_replacement_ages_out_date"] = (min(counted).replace(year=min(counted).year + 1)).isoformat() if not (min(counted).month == 2 and min(counted).day == 29) else min(counted).replace(year=min(counted).year + 1, day=28).isoformat()
    return result


def business_days_between(start, end):
    """Weekdays after the opening date through end date, excluding weekends only."""
    if start is None or end is None or end < start:
        return None
    cursor = start + timedelta(days=1)
    count = 0
    while cursor <= end:
        if cursor.weekday() < 5:
            count += 1
        cursor += timedelta(days=1)
    return count


def order_precheck(p):
    account = p.get("account") if isinstance(p.get("account"), dict) else {}
    now = parse_day(p.get("now"))
    opened = parse_day(account.get("date_opened"))
    blockers = []
    if not as_bool(p.get("verified")):
        blockers.append("customer_not_verified")
    if str(account.get("account_type", "")).lower() != "checking":
        blockers.append("account_not_checking")
    if str(account.get("status", "")).upper() != "OPEN":
        blockers.append("account_not_open")
    days = business_days_between(opened, now)
    if days is None or days < 3:
        blockers.append("account_not_open_three_business_days")
    try:
        balance = Decimal(str(account.get("balance")))
        if balance < Decimal("25"):
            blockers.append("balance_below_25")
    except (InvalidOperation, ValueError, TypeError):
        balance = None
        blockers.append("balance_unknown")
    if as_bool(p.get("has_active_card")):
        blockers.append("active_card_exists")
    if as_bool(p.get("has_pending_card")):
        blockers.append("pending_card_order_exists")
    if not as_bool(p.get("us_address_confirmed")):
        blockers.append("us_domestic_address_not_confirmed")
    return {"allowed": not blockers, "blockers": blockers, "business_days_open": days,
            "balance": money(balance) if balance is not None else None}


def main(payload):
    action = payload.get("action")
    if action == "closure_check":
        return closure_check(payload)
    if action == "replacement_quote":
        return replacement_quote(payload)
    if action == "order_precheck":
        return order_precheck(payload)
    return {"error": "unsupported_action", "supported_actions": ["closure_check", "replacement_quote", "order_precheck"]}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": "invalid_input", "message": str(exc)}))
