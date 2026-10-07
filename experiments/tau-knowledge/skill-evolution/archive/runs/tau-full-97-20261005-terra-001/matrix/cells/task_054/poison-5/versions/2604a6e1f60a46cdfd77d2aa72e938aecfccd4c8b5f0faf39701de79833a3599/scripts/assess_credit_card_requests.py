#!/usr/bin/env python3
"""Assess documented credit-card request criteria without performing bank actions.

Input: JSON object with optional now, dispute, replacement, and cli objects as
specified in SKILL.md. Output: JSON object whose statuses are eligible,
ineligible, unknown, or not_requested. Unknown means live information must be
retrieved before treating a requirement as satisfied.
"""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

TIER_ALIASES = {
    "entry": "entry", "entry-tier": "entry", "entry tier": "entry",
    "mid": "mid", "mid-tier": "mid", "mid tier": "mid",
    "premium": "premium", "premium-tier": "premium", "premium tier": "premium",
    "elite": "elite", "elite-tier": "elite", "elite tier": "elite",
    "invitation": "invitation", "invitation-tier": "invitation", "invitation tier": "invitation",
}
PROVISIONAL_MAX = {
    "entry": Decimal("2500"), "mid": Decimal("5000"),
    "premium": Decimal("10000"), "elite": Decimal("15000"),
    "invitation": Decimal("25000"),
}
CLI_RULES = {
    "entry": {"age": 120, "cooldown": 120, "utilization": Decimal("70"), "payment": 6, "max_fraction": Decimal("0.25")},
    "mid": {"age": 90, "cooldown": 90, "utilization": Decimal("80"), "payment": 3, "max_fraction": Decimal("0.50")},
    "premium": {"age": 60, "cooldown": 60, "utilization": Decimal("90"), "payment": 3, "max_fraction": Decimal("0.50")},
}
REPLACEMENT_LIMIT = {"entry": 2, "mid": 3, "premium": 4, "elite": 4, "invitation": 4}


def as_decimal(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return None


def parse_date(value):
    if value is None or not isinstance(value, str):
        return None
    value = value.strip()
    # Inputs may include timestamps; the first ten characters carry the date.
    candidates = (value, value[:10])
    for candidate in candidates:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    return None


def tier(value):
    if not isinstance(value, str):
        return None
    return TIER_ALIASES.get(value.strip().lower())


def status_from_checks(checks):
    values = list(checks.values())
    if any(v is False for v in values):
        return "ineligible"
    if any(v is None for v in values):
        return "unknown"
    return "eligible"


def age_check(opened, now, minimum):
    if opened is None or now is None:
        return None
    return (now - opened).days >= minimum


def dispute_assessment(data, now):
    if not isinstance(data, dict):
        return {"status": "not_requested"}
    t = tier(data.get("tier"))
    amount = as_decimal(data.get("transaction_amount"))
    opened = parse_date(data.get("account_open_date"))
    reason = data.get("reason")
    purchased = parse_date(data.get("purchase_date"))
    contacted = data.get("contacted_merchant")
    dates = data.get("dispute_dates")
    checks = {}
    checks["recognized_tier"] = t in PROVISIONAL_MAX
    checks["account_open_at_least_60_days"] = age_check(opened, now, 60)
    permitted = {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}
    checks["permitted_reason"] = reason in permitted if isinstance(reason, str) else None
    if reason == "goods_services_not_received":
        checks["goods_not_received_purchase_over_30_days"] = None if purchased is None or now is None else (now - purchased).days > 30
    checks["amount_at_least_25"] = None if amount is None else amount >= Decimal("25")
    checks["amount_within_tier_maximum"] = None if amount is None or t not in PROVISIONAL_MAX else amount <= PROVISIONAL_MAX[t]
    if isinstance(dates, list) and now is not None:
        parsed = [parse_date(x) for x in dates]
        checks["no_more_than_two_disputes_in_previous_12_months"] = None if any(x is None for x in parsed) else sum(x >= now - timedelta(days=365) and x <= now for x in parsed) <= 2
    else:
        checks["no_more_than_two_disputes_in_previous_12_months"] = None
    if reason == "unauthorized_fraudulent_charge":
        checks["merchant_contact_requirement"] = True
    elif isinstance(reason, str):
        checks["merchant_contact_requirement"] = contacted if isinstance(contacted, bool) else None
    else:
        checks["merchant_contact_requirement"] = None
    return {"status": status_from_checks(checks), "checks": checks, "tier_maximum": str(PROVISIONAL_MAX[t]) if t in PROVISIONAL_MAX else None}


def replacement_assessment(data):
    if not isinstance(data, dict):
        return {"status": "not_requested"}
    t = tier(data.get("tier"))
    pending = data.get("pending_order")
    count = data.get("orders_last_60_days")
    checks = {
        "recognized_tier": t in REPLACEMENT_LIMIT,
        "no_pending_replacement_order": (not pending) if isinstance(pending, bool) else None,
        "within_60_day_replacement_limit": (count < REPLACEMENT_LIMIT[t]) if isinstance(count, int) and not isinstance(count, bool) and t in REPLACEMENT_LIMIT else None,
    }
    return {"status": status_from_checks(checks), "checks": checks, "limit_in_60_days": REPLACEMENT_LIMIT.get(t)}


def cli_assessment(data, now):
    if not isinstance(data, dict):
        return {"status": "not_requested"}
    t = tier(data.get("tier"))
    rules = CLI_RULES.get(t)
    current = as_decimal(data.get("current_limit"))
    requested = as_decimal(data.get("requested_increase"))
    max_increase = current * rules["max_fraction"] if current is not None and rules else None
    amount_checks = {
        "recognized_cli_tier": rules is not None,
        "positive_current_limit": None if current is None else current > 0,
        "positive_requested_increase": None if requested is None else requested > 0,
        "requested_increase_within_maximum": None if requested is None or max_increase is None else requested <= max_increase,
    }
    submission_status = status_from_checks(amount_checks)
    opened = parse_date(data.get("account_open_date"))
    approved = parse_date(data.get("latest_approved_cli_date"))
    utilization = as_decimal(data.get("utilization_percent"))
    past_due = as_decimal(data.get("past_due_amount"))
    active_disputes = data.get("active_disputes")
    pending = data.get("pending_replacement")
    on_time = data.get("consecutive_on_time_months")
    post = {
        "account_age": age_check(opened, now, rules["age"]) if rules else None,
        "approved_request_cooldown_elapsed": None if approved is None or now is None or rules is None else (now - approved).days >= rules["cooldown"],
        "no_active_disputes": (active_disputes == 0) if isinstance(active_disputes, int) and not isinstance(active_disputes, bool) else None,
        "no_pending_replacement": (not pending) if isinstance(pending, bool) else None,
        "no_past_due_balance": None if past_due is None else past_due <= 0,
        "utilization_strictly_below_threshold": None if utilization is None or rules is None else utilization < rules["utilization"],
        "required_consecutive_on_time_payments": (on_time >= rules["payment"]) if isinstance(on_time, int) and not isinstance(on_time, bool) and rules else None,
    }
    failed_reason = None
    reason_order = [
        ("account_age", "insufficient_account_age"),
        ("approved_request_cooldown_elapsed", "cooldown_period_active"),
        ("no_active_disputes", "pending_disputes"),
        ("no_pending_replacement", "pending_replacement_card"),
        ("no_past_due_balance", "past_due_balance"),
        ("utilization_strictly_below_threshold", "high_utilization"),
        ("required_consecutive_on_time_payments", "insufficient_payment_history"),
    ]
    for key, reason in reason_order:
        if post[key] is False:
            failed_reason = reason
            break
    return {
        "status": status_from_checks(post) if submission_status == "eligible" else "amount_not_valid_for_submission",
        "submission_status": submission_status,
        "amount_checks": amount_checks,
        "post_submission_checks": post,
        "maximum_increase": str(max_increase) if max_increase is not None else None,
        "new_credit_limit_if_approved": str(current + requested) if current is not None and requested is not None else None,
        "suggested_denial_reason_if_submitted": failed_reason,
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        return
    now = parse_date(payload.get("now"))
    output = {
        "now_parsed": now.isoformat() if now else None,
        "provisional_credit": dispute_assessment(payload.get("dispute"), now),
        "replacement": replacement_assessment(payload.get("replacement")),
        "cli": cli_assessment(payload.get("cli"), now),
        "note": "This assessment is advisory. Required banking-tool calls and required workflow order remain mandatory.",
    }
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
