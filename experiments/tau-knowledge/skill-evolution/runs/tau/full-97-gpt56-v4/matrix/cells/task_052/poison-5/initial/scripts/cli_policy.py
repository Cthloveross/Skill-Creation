#!/usr/bin/env python3
"""Deterministic CLI policy calculations.

Input JSON fields:
 card_tier: entry|mid|premium
 current_credit_limit, current_balance, past_due_amount: numbers
 requested: {"kind": "dollars"|"percent", "value": number}
 account_open_date, current_time, last_approved_request_date: ISO-like dates/timestamps
 has_active_disputes, has_nonfinal_replacement_order: booleans (optional)
 payment_history_consecutive_on_time_months: integer (optional)

Output JSON reports values and each check as true, false, or null when unknown.
No banking tool is called by this program.
"""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

POLICY = {
    "entry": {"age": 120, "cooldown": 120, "util": Decimal("70"), "months": 6, "max_pct": Decimal("25")},
    "mid": {"age": 90, "cooldown": 90, "util": Decimal("80"), "months": 3, "max_pct": Decimal("50")},
    "premium": {"age": 60, "cooldown": 60, "util": Decimal("90"), "months": 3, "max_pct": Decimal("50")},
}


def dec(value, name):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{name} must be numeric")


def parse_day(value, name):
    if value in (None, ""):
        return None
    text = str(value).strip()
    # Inputs often include a timezone label; dates alone are sufficient for policy days.
    for candidate in (text[:10], text):
        try:
            return datetime.fromisoformat(candidate.replace("Z", "+00:00")).date()
        except ValueError:
            pass
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    raise ValueError(f"{name} must begin with a supported date")


def money(d):
    return str(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def main(data):
    tier = str(data.get("card_tier", "")).lower().replace("-tier", "").strip()
    if tier not in POLICY:
        raise ValueError("card_tier must be entry, mid, or premium")
    p = POLICY[tier]
    limit = dec(data.get("current_credit_limit"), "current_credit_limit")
    if limit <= 0:
        raise ValueError("current_credit_limit must be positive")
    requested = data.get("requested")
    if not isinstance(requested, dict):
        raise ValueError("requested must be an object")
    kind = requested.get("kind")
    value = dec(requested.get("value"), "requested.value")
    if value <= 0:
        raise ValueError("requested.value must be positive")
    if kind == "dollars":
        increase = value
    elif kind == "percent":
        increase = limit * value / Decimal("100")
    else:
        raise ValueError("requested.kind must be dollars or percent")
    maximum = limit * p["max_pct"] / Decimal("100")

    now = parse_day(data.get("current_time"), "current_time")
    opened = parse_day(data.get("account_open_date"), "account_open_date")
    account_age_days = (now - opened).days if now and opened else None
    last_approved = parse_day(data.get("last_approved_request_date"), "last_approved_request_date")
    cooldown_end = last_approved + timedelta(days=p["cooldown"]) if last_approved else None

    balance = dec(data.get("current_balance"), "current_balance") if data.get("current_balance") is not None else None
    utilization = balance * Decimal("100") / limit if balance is not None else None
    past_due = dec(data.get("past_due_amount"), "past_due_amount") if data.get("past_due_amount") is not None else None
    payments = data.get("payment_history_consecutive_on_time_months")
    if payments is not None:
        if not isinstance(payments, int) or isinstance(payments, bool):
            raise ValueError("payment_history_consecutive_on_time_months must be an integer")

    checks = {
        "requested_amount_within_limit": increase <= maximum,
        "account_age": account_age_days >= p["age"] if account_age_days is not None else None,
        "cooldown": now >= cooldown_end if cooldown_end else True,
        "active_disputes_clear": (not data["has_active_disputes"]) if "has_active_disputes" in data else None,
        "replacement_orders_clear": (not data["has_nonfinal_replacement_order"]) if "has_nonfinal_replacement_order" in data else None,
        "past_due_clear": past_due <= 0 if past_due is not None else None,
        "utilization": utilization < p["util"] if utilization is not None else None,
        "payment_history": payments >= p["months"] if payments is not None else None,
    }
    reason_by_check = {
        "requested_amount_within_limit": "requested_amount_exceeds_limit",
        "account_age": "insufficient_account_age",
        "cooldown": "cooldown_period_active",
        "active_disputes_clear": "pending_disputes",
        "replacement_orders_clear": "pending_replacement_card",
        "past_due_clear": "past_due_balance",
        "utilization": "high_utilization",
        "payment_history": "insufficient_payment_history",
    }
    failure = next((key for key, passed in checks.items() if passed is False), None)
    unknown = [key for key, passed in checks.items() if passed is None]
    output = {
        "card_tier": tier,
        "required": {"minimum_account_age_days": p["age"], "cooldown_days": p["cooldown"], "utilization_must_be_below_percent": str(p["util"]), "required_consecutive_on_time_months": p["months"], "maximum_increase_percent": str(p["max_pct"])},
        "requested_increase_amount": money(increase),
        "maximum_increase_amount": money(maximum),
        "proposed_new_credit_limit": money(limit + increase),
        "account_age_days": account_age_days,
        "utilization_percent": str(utilization.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)) if utilization is not None else None,
        "cooldown_eligible_on": cooldown_end.isoformat() if cooldown_end else None,
        "checks": checks,
        "unknown_checks": unknown,
        "all_checks_pass": all(value is True for value in checks.values()),
        "recommended_denial_reason": reason_by_check.get(failure, "other" if unknown else None),
    }
    return output


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
