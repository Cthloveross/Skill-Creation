#!/usr/bin/env python3
"""Assess normalized credit-limit-increase policy inputs from JSON stdin."""

import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_DOWN

POLICY = {
    "entry": {
        "age_days": 120,
        "cooldown_days": 120,
        "utilization_threshold": Decimal("70"),
        "payment_months": 6,
        "maximum_fraction": Decimal("0.25"),
    },
    "mid": {
        "age_days": 90,
        "cooldown_days": 90,
        "utilization_threshold": Decimal("80"),
        "payment_months": 3,
        "maximum_fraction": Decimal("0.50"),
    },
    "premium": {
        "age_days": 60,
        "cooldown_days": 60,
        "utilization_threshold": Decimal("90"),
        "payment_months": 3,
        "maximum_fraction": Decimal("0.50"),
    },
}

DENIAL_ORDER = (
    ("account_age", "insufficient_account_age"),
    ("cooldown", "cooldown_period_active"),
    ("disputes", "pending_disputes"),
    ("replacement_orders", "pending_replacement_card"),
    ("good_standing", "past_due_balance"),
    ("utilization", "high_utilization"),
    ("payment_history", "insufficient_payment_history"),
)


def parse_date(value):
    """Return a date from an ISO date/timestamp or MM/DD/YYYY string."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("date must be a nonempty string")
    text = value.strip()
    for form in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S %Z"):
        try:
            return datetime.strptime(text, form).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError("unsupported date format") from exc


def read_decimal(data, key, errors, positive=False):
    try:
        value = Decimal(str(data[key]))
        if not value.is_finite() or value < 0 or (positive and value <= 0):
            raise ValueError
        return value
    except (KeyError, InvalidOperation, ValueError):
        errors.append(key)
        return None


def read_bool(data, key, errors):
    value = data.get(key)
    if type(value) is not bool:
        errors.append(key)
        return None
    return value


def emit(value):
    print(json.dumps(value, sort_keys=True))


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("top-level value must be an object")
    except Exception as exc:
        emit({"status": "insufficient_data", "error": "invalid_json", "detail": str(exc)})
        return

    errors = []
    raw_tier = data.get("tier")
    tier = raw_tier.lower().replace("-tier", "") if isinstance(raw_tier, str) else None
    if tier not in POLICY:
        errors.append("tier")
        tier = None

    dates = {}
    for key in ("now", "account_open_date"):
        try:
            dates[key] = parse_date(data.get(key))
        except ValueError:
            errors.append(key)

    limit = read_decimal(data, "current_credit_limit", errors, positive=True)
    balance = read_decimal(data, "current_balance", errors)
    requested = read_decimal(data, "requested_increase_amount", errors, positive=True)
    past_due = read_decimal(data, "past_due_amount", errors)
    submitted = read_bool(data, "submission_recorded", errors)
    current = read_bool(data, "is_current", errors)
    disputes = read_bool(data, "active_disputes", errors)

    payment_months = data.get("consecutive_on_time_months")
    if type(payment_months) is not int or payment_months < 0:
        errors.append("consecutive_on_time_months")
        payment_months = None

    replacement_statuses = data.get("replacement_order_statuses")
    if not isinstance(replacement_statuses, list) or not all(
        isinstance(status, str) and status.strip() for status in replacement_statuses
    ):
        errors.append("replacement_order_statuses")
        replacement_statuses = None

    approved_dates = data.get("approved_request_dates")
    parsed_approved_dates = []
    if not isinstance(approved_dates, list):
        errors.append("approved_request_dates")
    else:
        for index, value in enumerate(approved_dates):
            try:
                parsed_approved_dates.append(parse_date(value))
            except ValueError:
                errors.append("approved_request_dates[%d]" % index)

    result = {
        "checks": {},
        "cooldown_eligible_on": None,
        "denial_reason": None,
        "missing_or_invalid": errors,
        "tier": tier,
    }
    if tier:
        policy = POLICY[tier]
        result["policy"] = {
            "cooldown_days": policy["cooldown_days"],
            "maximum_increase_fraction": str(policy["maximum_fraction"]),
            "maximum_utilization_percent_exclusive": str(policy["utilization_threshold"]),
            "minimum_account_age_days": policy["age_days"],
            "required_consecutive_on_time_months": policy["payment_months"],
        }

    # Amount validation is intentionally evaluated before the submission state.
    if tier and limit is not None and requested is not None:
        maximum = (limit * POLICY[tier]["maximum_fraction"]).quantize(
            Decimal("0.01"), rounding=ROUND_DOWN
        )
        result["maximum_increase_amount"] = str(maximum)
        result["proposed_new_credit_limit"] = str((limit + requested).quantize(Decimal("0.01")))
        amount_ok = requested == requested.to_integral_value() and requested <= maximum
        result["checks"]["requested_amount"] = amount_ok
        if not amount_ok:
            result["status"] = "needs_amount_adjustment"
            emit(result)
            return

    if errors:
        result["status"] = "insufficient_data"
        emit(result)
        return

    now = dates["now"]
    opened = dates["account_open_date"]
    if opened > now:
        result["missing_or_invalid"].append("account_open_date_after_now")
        result["status"] = "insufficient_data"
        emit(result)
        return

    assert tier is not None and limit is not None and balance is not None
    assert requested is not None and submitted is not None and current is not None
    assert past_due is not None and disputes is not None
    assert payment_months is not None and replacement_statuses is not None

    policy = POLICY[tier]
    age_days = (now - opened).days
    utilization = balance / limit * Decimal("100")
    latest_approved = max(parsed_approved_dates) if parsed_approved_dates else None
    cooldown_ok = True
    if latest_approved is not None:
        eligible_on = latest_approved + timedelta(days=policy["cooldown_days"])
        cooldown_ok = now >= eligible_on
        result["latest_approved_request_date"] = latest_approved.isoformat()
        result["cooldown_eligible_on"] = eligible_on.isoformat()

    final_statuses = {"delivered", "cancelled"}
    has_pending_replacement = any(
        status.strip().lower() not in final_statuses for status in replacement_statuses
    )
    result["account_age_days"] = age_days
    result["utilization_percent"] = str(utilization.quantize(Decimal("0.01")))
    result["checks"].update({
        "account_age": age_days >= policy["age_days"],
        "cooldown": cooldown_ok,
        "disputes": not disputes,
        "replacement_orders": not has_pending_replacement,
        "good_standing": current and past_due == 0,
        "utilization": utilization < policy["utilization_threshold"],
        "payment_history": payment_months >= policy["payment_months"],
    })

    if not submitted:
        result["status"] = "awaiting_submission"
    elif all(result["checks"].values()):
        result["status"] = "ready_to_approve"
    else:
        result["status"] = "ready_to_deny"
        for check, reason in DENIAL_ORDER:
            if not result["checks"][check]:
                result["denial_reason"] = reason
                break

    emit(result)


if __name__ == "__main__":
    main()
