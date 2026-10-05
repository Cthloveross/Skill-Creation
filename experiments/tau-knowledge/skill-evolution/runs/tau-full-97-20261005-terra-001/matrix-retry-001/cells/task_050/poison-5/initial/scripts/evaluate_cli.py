#!/usr/bin/env python3
"""Deterministically evaluate supplied CLI facts; does not call banking tools.

stdin schema: JSON object with tier, current_limit, requested_increase, opened_on,
now; optional current_balance, last_approved_request_on, payment_history_pass,
has_active_dispute, has_pending_replacement, and is_past_due. Dates accept
YYYY-MM-DD, ISO datetime/date prefixes, or MM/DD/YYYY. stdout is one JSON object.
"""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

RULES = {
    "entry": {"age_days": 120, "cooldown_days": 120, "utilization_lt": Decimal("70"), "payment_months": 6, "max_fraction": Decimal("0.25")},
    "mid": {"age_days": 90, "cooldown_days": 90, "utilization_lt": Decimal("80"), "payment_months": 3, "max_fraction": Decimal("0.50")},
    "premium": {"age_days": 60, "cooldown_days": 60, "utilization_lt": Decimal("90"), "payment_months": 3, "max_fraction": Decimal("0.50")},
}


def parse_date(value):
    if value is None or value == "":
        return None
    text = str(value).strip()
    for candidate in (text[:10], text):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    raise ValueError("invalid date: %s" % text)


def money(value, field, errors):
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return amount
    except (InvalidOperation, ValueError):
        errors.append("%s must be numeric" % field)
        return None


def main(data):
    errors = []
    tier = str(data.get("tier", "")).strip().lower().replace("-tier", "").replace("_tier", "")
    if tier not in RULES:
        errors.append("tier must be entry, mid, or premium")
        return {"input_errors": errors, "decision": "needs_data"}
    rule = RULES[tier]
    limit = money(data.get("current_limit"), "current_limit", errors)
    requested = money(data.get("requested_increase"), "requested_increase", errors)
    balance = money(data.get("current_balance"), "current_balance", errors) if "current_balance" in data else None
    try:
        opened = parse_date(data.get("opened_on"))
        today = parse_date(data.get("now"))
        last_approved = parse_date(data.get("last_approved_request_on"))
    except ValueError as exc:
        errors.append(str(exc))
        opened = today = last_approved = None
    if not opened:
        errors.append("opened_on is required")
    if not today:
        errors.append("now is required")
    if limit is not None and limit <= 0:
        errors.append("current_limit must be greater than zero")
    if requested is not None:
        if requested <= 0:
            errors.append("requested_increase must be greater than zero")
        if requested != requested.to_integral_value():
            errors.append("requested_increase must be a whole-dollar amount")

    maximum = (limit * rule["max_fraction"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if limit and limit > 0 else None
    age_date = opened + timedelta(days=rule["age_days"]) if opened else None
    cooldown_end = last_approved + timedelta(days=rule["cooldown_days"]) if last_approved else None
    utilization = ((balance / limit) * Decimal("100")) if balance is not None and limit and limit > 0 else None
    checks = {
        "requested_amount": (requested <= maximum) if requested is not None and maximum is not None else None,
        "account_age": (today >= age_date) if today and age_date else None,
        "cooldown": (today >= cooldown_end) if today and cooldown_end else (True if today else None),
        "utilization": (utilization < rule["utilization_lt"]) if utilization is not None else None,
        "payment_history": data.get("payment_history_pass") if isinstance(data.get("payment_history_pass"), bool) else None,
        "active_disputes": (not data["has_active_dispute"]) if isinstance(data.get("has_active_dispute"), bool) else None,
        "pending_replacement": (not data["has_pending_replacement"]) if isinstance(data.get("has_pending_replacement"), bool) else None,
        "good_standing": (not data["is_past_due"]) if isinstance(data.get("is_past_due"), bool) else None,
    }
    if checks["requested_amount"] is False:
        decision, reason = "request_amendment_before_submission", "requested_amount_exceeds_limit"
    elif errors or any(v is None for v in checks.values()):
        decision, reason = "needs_data", None
    elif all(checks.values()):
        decision, reason = "eligible_after_submission", None
    else:
        reason_map = [
            ("account_age", "insufficient_account_age"), ("cooldown", "cooldown_period_active"),
            ("active_disputes", "pending_disputes"), ("pending_replacement", "pending_replacement_card"),
            ("good_standing", "past_due_balance"), ("utilization", "high_utilization"),
            ("payment_history", "insufficient_payment_history"),
        ]
        reason = next(reason for key, reason in reason_map if checks[key] is False)
        decision = "deny_after_submission"
    result = {
        "input_errors": errors, "tier": tier,
        "requirements": {"minimum_age_days": rule["age_days"], "cooldown_days": rule["cooldown_days"], "utilization_must_be_below_percent": str(rule["utilization_lt"]), "payment_months": rule["payment_months"], "maximum_fraction_of_current_limit": str(rule["max_fraction"])},
        "maximum_increase": str(maximum) if maximum is not None else None,
        "new_credit_limit_if_approved": str((limit + requested).quantize(Decimal("0.01"))) if limit is not None and requested is not None else None,
        "account_age_qualifies_on": age_date.isoformat() if age_date else None,
        "cooldown_ends_on": cooldown_end.isoformat() if cooldown_end else None,
        "utilization_percent": str(utilization.quantize(Decimal("0.0001"))) if utilization is not None else None,
        "checks": checks, "decision": decision, "denial_reason": reason,
    }
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"input_errors": [str(exc)], "decision": "needs_data"}, sort_keys=True))
