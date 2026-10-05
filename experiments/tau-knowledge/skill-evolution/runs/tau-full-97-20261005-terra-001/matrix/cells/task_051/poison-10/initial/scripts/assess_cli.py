#!/usr/bin/env python3
"""Assess normalized CLI eligibility inputs; reads JSON stdin and emits JSON stdout."""

import json
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_DOWN

POLICY = {
    "entry": {"age_days": 120, "cooldown_days": 120, "utilization_pct": Decimal("70"),
              "payment_months": 6, "maximum_fraction": Decimal("0.25")},
    "mid": {"age_days": 90, "cooldown_days": 90, "utilization_pct": Decimal("80"),
            "payment_months": 3, "maximum_fraction": Decimal("0.50")},
    "premium": {"age_days": 60, "cooldown_days": 60, "utilization_pct": Decimal("90"),
                "payment_months": 3, "maximum_fraction": Decimal("0.50")},
}

DENIAL_ORDER = [
    ("account_age", "insufficient_account_age"),
    ("cooldown", "cooldown_period_active"),
    ("disputes", "pending_disputes"),
    ("replacement_orders", "pending_replacement_card"),
    ("good_standing", "past_due_balance"),
    ("utilization", "high_utilization"),
    ("payment_history", "insufficient_payment_history"),
]


def parse_date(value):
    """Return a calendar date for supported date/timestamp representations."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError("must be a nonempty date string")
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S %Z"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError("must be an ISO date/timestamp or MM/DD/YYYY") from exc


def decimal_value(data, field, errors, nonnegative=True):
    try:
        value = Decimal(str(data[field]))
        if not value.is_finite() or (nonnegative and value < 0):
            raise ValueError
        return value
    except (KeyError, InvalidOperation, ValueError):
        errors.append(field)
        return None


def bool_value(data, field, errors):
    value = data.get(field)
    if type(value) is not bool:
        errors.append(field)
        return None
    return value


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("top-level JSON must be an object")
    except Exception as exc:
        print(json.dumps({"status": "insufficient_data", "error": "invalid_json", "detail": str(exc)}))
        return

    errors = []
    tier_raw = data.get("tier")
    tier = tier_raw.lower().replace("-tier", "") if isinstance(tier_raw, str) else None
    if tier not in POLICY:
        errors.append("tier")
        tier = None

    now = opened = None
    for field in ("now", "account_open_date"):
        try:
            parsed = parse_date(data.get(field))
            if field == "now":
                now = parsed
            else:
                opened = parsed
        except ValueError:
            errors.append(field)

    limit = decimal_value(data, "current_credit_limit", errors)
    balance = decimal_value(data, "current_balance", errors)
    requested = decimal_value(data, "requested_increase_amount", errors)
    past_due = decimal_value(data, "past_due_amount", errors)
    is_current = bool_value(data, "is_current", errors)
    submitted = bool_value(data, "submission_recorded", errors)
    active_disputes = bool_value(data, "active_disputes", errors)

    statuses = data.get("replacement_order_statuses")
    if not isinstance(statuses, list) or not all(isinstance(x, str) and x.strip() for x in statuses):
        errors.append("replacement_order_statuses")
        statuses = None

    payment_months = data.get("consecutive_on_time_months")
    if type(payment_months) is not int or payment_months < 0:
        errors.append("consecutive_on_time_months")
        payment_months = None

    approved_dates = data.get("approved_request_dates")
    parsed_approved = []
    if not isinstance(approved_dates, list):
        errors.append("approved_request_dates")
    else:
        for index, raw_date in enumerate(approved_dates):
            try:
                parsed_approved.append(parse_date(raw_date))
            except ValueError:
                errors.append("approved_request_dates[%d]" % index)

    output = {
        "tier": tier,
        "missing_or_invalid": errors,
        "checks": {},
        "denial_reason": None,
        "cooldown_eligible_on": None,
    }
    if tier:
        policy = POLICY[tier]
        output["policy"] = {
            "minimum_account_age_days": policy["age_days"],
            "cooldown_days": policy["cooldown_days"],
            "maximum_utilization_percent_exclusive": str(policy["utilization_pct"]),
            "required_consecutive_on_time_months": policy["payment_months"],
            "maximum_increase_fraction": str(policy["maximum_fraction"]),
        }

    # Amount validation precedes submission and eligibility determination.
    if tier and limit is not None and requested is not None:
        maximum = (limit * POLICY[tier]["maximum_fraction"]).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        output["maximum_increase_amount"] = str(maximum)
        output["proposed_new_credit_limit"] = str((limit + requested).quantize(Decimal("0.01")))
        amount_ok = requested > 0 and requested <= maximum and requested == requested.to_integral_value()
        output["checks"]["requested_amount"] = amount_ok
        if not amount_ok:
            output["status"] = "needs_amount_adjustment"
            output["message"] = "A positive whole-dollar amount at or below the calculated maximum must be confirmed before submission."
            print(json.dumps(output, sort_keys=True))
            return

    if errors:
        output["status"] = "insufficient_data"
        print(json.dumps(output, sort_keys=True))
        return

    assert tier and now and opened and limit is not None and balance is not None
    assert past_due is not None and is_current is not None and submitted is not None
    assert active_disputes is not None and statuses is not None and payment_months is not None
    policy = POLICY[tier]

    if opened > now:
        output["missing_or_invalid"].append("account_open_date_after_now")
        output["status"] = "insufficient_data"
        print(json.dumps(output, sort_keys=True))
        return

    age_days = (now - opened).days
    utilization = (balance / limit * Decimal("100")) if limit > 0 else None
    if limit <= 0:
        output["missing_or_invalid"].append("current_credit_limit_must_be_positive")
        output["status"] = "insufficient_data"
        print(json.dumps(output, sort_keys=True))
        return

    latest_approved = max(parsed_approved) if parsed_approved else None
    cooldown_ok = True
    eligible_on = None
    if latest_approved is not None:
        eligible_on = latest_approved + timedelta(days=policy["cooldown_days"])
        cooldown_ok = now >= eligible_on
        output["latest_approved_request_date"] = latest_approved.isoformat()
        output["cooldown_eligible_on"] = eligible_on.isoformat()

    final_replacement_statuses = {"delivered", "cancelled"}
    has_pending_replacement = any(status.strip().lower() not in final_replacement_statuses for status in statuses)
    checks = output["checks"]
    checks.update({
        "account_age": age_days >= policy["age_days"],
        "cooldown": cooldown_ok,
        "disputes": not active_disputes,
        "replacement_orders": not has_pending_replacement,
        "good_standing": is_current and past_due == 0,
        "utilization": utilization < policy["utilization_pct"],
        "payment_history": payment_months >= policy["payment_months"],
    })
    output["account_age_days"] = age_days
    output["utilization_percent"] = str(utilization.quantize(Decimal("0.01")))

    if not submitted:
        output["status"] = "awaiting_submission"
    elif all(checks.values()):
        output["status"] = "ready_to_approve"
    else:
        output["status"] = "ready_to_deny"
        for check_name, reason in DENIAL_ORDER:
            if not checks[check_name]:
                output["denial_reason"] = reason
                break

    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
