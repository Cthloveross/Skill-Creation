#!/usr/bin/env python3
"""Deterministically evaluate CLI rules; reads JSON stdin and writes JSON stdout."""
import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

RULES = {
    "Entry-tier": {"age": 120, "cooldown": 120, "utilization": Decimal("70"), "maximum_fraction": Decimal("0.25"), "payments": 6},
    "Mid-tier": {"age": 90, "cooldown": 90, "utilization": Decimal("80"), "maximum_fraction": Decimal("0.50"), "payments": 3},
    "Premium-tier": {"age": 60, "cooldown": 60, "utilization": Decimal("90"), "maximum_fraction": Decimal("0.50"), "payments": 3},
}
FAILURE_REASON = {
    "account_age": "insufficient_account_age",
    "cooldown": "cooldown_period_active",
    "active_disputes": "pending_disputes",
    "pending_replacement_orders": "pending_replacement_card",
    "past_due_balance": "past_due_balance",
    "utilization": "high_utilization",
    "payment_history": "insufficient_payment_history",
}
ORDER = ["account_age", "cooldown", "active_disputes", "pending_replacement_orders", "past_due_balance", "utilization", "payment_history"]


def as_date(value):
    if value is None or value == "":
        return None
    text = str(value).strip()
    # Dates from tools may be ISO dates or ISO-like timestamps with a timezone label.
    for candidate in (text[:10], text):
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass
    for fmt in ("%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    return None


def decimal_value(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def known_bool(value):
    return value if isinstance(value, bool) else None


def check(value, message=None):
    return {"status": "pass" if value is True else "fail" if value is False else "unknown", "detail": message}


def main(data):
    tier = data.get("tier")
    if tier not in RULES:
        return {"error": "tier must be Entry-tier, Mid-tier, or Premium-tier"}
    rules = RULES[tier]
    today = as_date(data.get("current_date"))
    opened = as_date(data.get("account_open_date"))
    limit = decimal_value(data.get("current_credit_limit"))
    balance = decimal_value(data.get("current_balance"))
    requested = decimal_value(data.get("requested_increase_amount"))

    result = {"tier": tier, "requirements": {"minimum_account_age_days": rules["age"], "cooldown_days": rules["cooldown"], "maximum_utilization_percent_exclusive": str(rules["utilization"]), "payment_months": rules["payments"]}}
    if limit is not None and limit > 0:
        maximum = limit * rules["maximum_fraction"]
        result["maximum_increase_amount"] = float(maximum)
    else:
        maximum = None
        result["maximum_increase_amount"] = None

    whole_dollar = requested is not None and requested == requested.to_integral_value()
    amount_ok = requested is not None and requested > 0 and whole_dollar and maximum is not None and requested <= maximum
    if amount_ok:
        result["amount_disposition"] = "valid"
    elif requested is not None and maximum is not None and requested > maximum:
        result["amount_disposition"] = "exceeds_maximum_do_not_submit"
    else:
        result["amount_disposition"] = "invalid_or_unverifiable_do_not_submit"
    result["requested_increase_amount"] = float(requested) if requested is not None else None

    checks = {}
    age_days = (today - opened).days if today and opened else None
    checks["account_age"] = check(None if age_days is None else age_days >= rules["age"], "account_age_days=" + str(age_days) if age_days is not None else "missing valid current or open date")
    result["account_age_days"] = age_days

    approved_dates = [as_date(x) for x in data.get("prior_approved_request_dates", [])]
    approved_dates = [x for x in approved_dates if x is not None]
    last_approved = max(approved_dates) if approved_dates else None
    cooldown_days = (today - last_approved).days if today and last_approved else None
    checks["cooldown"] = check(True if last_approved is None else (None if cooldown_days is None else cooldown_days >= rules["cooldown"]), "no prior approved request" if last_approved is None else "days_since_prior_approved_request=" + str(cooldown_days))
    result["days_since_prior_approved_request"] = cooldown_days

    for key in ("active_disputes", "pending_replacement_orders", "past_due_balance"):
        value = known_bool(data.get(key))
        checks[key] = check(None if value is None else not value, "not reliably verified" if value is None else None)

    utilization = (balance / limit * Decimal("100")) if balance is not None and limit is not None and limit > 0 else None
    checks["utilization"] = check(None if utilization is None else utilization < rules["utilization"], "utilization_percent=" + str(utilization) if utilization is not None else "missing valid balance or positive limit")
    result["utilization_percent"] = float(utilization) if utilization is not None else None

    months = data.get("consecutive_on_time_months")
    valid_months = isinstance(months, int) and not isinstance(months, bool) and months >= 0
    checks["payment_history"] = check(months >= rules["payments"] if valid_months else None, "consecutive_on_time_months=" + str(months) if valid_months else "not reliably verified")
    result["checks"] = checks

    failures = [key for key in ORDER if checks[key]["status"] == "fail"]
    unknown = [key for key in ORDER if checks[key]["status"] == "unknown"]
    result["established_failures"] = failures
    result["unverified_checks"] = unknown
    if result["amount_disposition"] != "valid":
        result["post_submission_action"] = "do_not_submit"
        result["denial_reason"] = None
    elif unknown:
        result["post_submission_action"] = "incomplete"
        result["denial_reason"] = None
    elif failures:
        result["post_submission_action"] = "deny"
        result["denial_reason"] = FAILURE_REASON[failures[0]]
    else:
        result["post_submission_action"] = "approve"
        result["denial_reason"] = None
        result["new_credit_limit"] = float(limit + requested)
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
