#!/usr/bin/env python3
"""Deterministically evaluate normalized credit-limit-increase policy facts.

Reads one JSON object from stdin and writes one JSON object to stdout. It makes no
network, filesystem, banking, or agent-tool calls.

Input fields: card_tier (or card_type='Gold Rewards Card'), current_credit_limit,
requested_increase_amount, account_open_date, as_of_date,
last_approved_request_submitted_date, current_balance or utilization_percent,
has_active_disputes, has_pending_replacement, is_current_no_past_due, and
consecutive_on_time_months. Dates accept YYYY-MM-DD or MM/DD/YYYY.
"""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

POLICY = {
    "entry-tier": (120, 120, Decimal("70"), 6, Decimal(".25")),
    "mid-tier": (90, 90, Decimal("80"), 3, Decimal(".50")),
    "premium-tier": (60, 60, Decimal("90"), 3, Decimal(".50")),
}
FAILURES = (
    ("account_age", "insufficient_account_age"),
    ("cooldown", "cooldown_period_active"),
    ("active_disputes", "pending_disputes"),
    ("replacement_card", "pending_replacement_card"),
    ("good_standing", "past_due_balance"),
    ("utilization", "high_utilization"),
    ("payment_history", "insufficient_payment_history"),
)

def dec(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        text = str(value).strip().replace("$", "").replace(",", "").replace("%", "")
        return Decimal(text) if text else None
    except (InvalidOperation, ValueError):
        return None

def parsed_date(value):
    if value is None:
        return None
    text = str(value).strip()
    for candidate in (text[:10], text):
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass
    try:
        return datetime.strptime(text, "%m/%d/%Y").date()
    except ValueError:
        return None

def number(value):
    return float(value) if value is not None else None

def bool_state(value, fails_when_true=False):
    if not isinstance(value, bool):
        return "unknown"
    failed = value if fails_when_true else not value
    return "fail" if failed else "pass"

def evaluate(data):
    tier = str(data.get("card_tier", "")).strip().lower()
    if tier not in POLICY and data.get("card_type") == "Gold Rewards Card":
        tier = "premium-tier"
    errors = []
    rule = POLICY.get(tier)
    if rule is None:
        errors.append("A supported, verified card tier is required.")
        age_min = cool_days = pay_min = None
        util_max = fraction = None
    else:
        age_min, cool_days, util_max, pay_min, fraction = rule

    limit = dec(data.get("current_credit_limit"))
    requested = dec(data.get("requested_increase_amount"))
    whole = requested is not None and requested == requested.to_integral_value()
    if limit is None or limit <= 0:
        errors.append("current_credit_limit must be a positive number.")
    if requested is None or not whole or requested <= 0:
        errors.append("requested_increase_amount must be a positive whole-dollar amount.")
    maximum = limit * fraction if limit is not None and fraction is not None else None
    exceeds = bool(maximum is not None and whole and requested > maximum)
    can_submit = not errors and not exceeds
    proposed = limit + requested if limit is not None and whole and requested and requested > 0 else None

    opened, today = parsed_date(data.get("account_open_date")), parsed_date(data.get("as_of_date"))
    if age_min is not None and opened and today and today >= opened:
        days = (today - opened).days
        age_state = "pass" if days >= age_min else "fail"
        age_eligible = (opened + timedelta(days=age_min)).isoformat()
    else:
        days, age_state, age_eligible = None, "unknown", None
    checks = [{"name":"account_age", "state":age_state, "age_days":days,
               "minimum_days":age_min, "eligible_on":age_eligible}]

    prior = parsed_date(data.get("last_approved_request_submitted_date"))
    if cool_days is None or today is None:
        cool_state, cool_eligible = "unknown", None
    elif prior is None:
        cool_state, cool_eligible = "pass", None
    else:
        cool_eligible = (prior + timedelta(days=cool_days)).isoformat()
        cool_state = "pass" if today >= parsed_date(cool_eligible) else "fail"
    checks.append({"name":"cooldown", "state":cool_state,
                   "prior_approved_submission_date":prior.isoformat() if prior else None,
                   "eligible_on":cool_eligible, "required_days":cool_days})

    checks.append({"name":"active_disputes", "state":bool_state(data.get("has_active_disputes"), True)})
    checks.append({"name":"replacement_card", "state":bool_state(data.get("has_pending_replacement"), True)})
    checks.append({"name":"good_standing", "state":bool_state(data.get("is_current_no_past_due"))})

    utilization = dec(data.get("utilization_percent"))
    if utilization is None:
        balance = dec(data.get("current_balance"))
        if balance is not None and limit is not None and limit > 0:
            utilization = balance * Decimal("100") / limit
    util_state = "unknown"
    if util_max is not None and utilization is not None and utilization >= 0:
        util_state = "pass" if utilization < util_max else "fail"
    checks.append({"name":"utilization", "state":util_state,
                   "utilization_percent":number(utilization),
                   "must_be_below_percent":number(util_max)})

    months = data.get("consecutive_on_time_months")
    try:
        months = None if isinstance(months, bool) or months is None else int(months)
    except (ValueError, TypeError):
        months = None
    payment_state = "unknown"
    if pay_min is not None and months is not None and months >= 0:
        payment_state = "pass" if months >= pay_min else "fail"
    checks.append({"name":"payment_history", "state":payment_state,
                   "consecutive_on_time_months":months, "required_months":pay_min})

    states = {item["name"]: item["state"] for item in checks}
    failure = next((reason for name, reason in FAILURES if states[name] == "fail"), None)
    unknown = any(item["state"] == "unknown" for item in checks)
    if not can_submit:
        decision = "do_not_submit"
        next_action = "ask_customer_to_adjust" if exceeds else "obtain_valid_pre_submission_facts"
        denial_reason = "requested_amount_exceeds_limit" if exceeds else None
    elif unknown:
        decision, next_action, denial_reason = "incomplete", "complete_required_eligibility_checks", None
    elif failure:
        decision, next_action, denial_reason = "deny", "deny_submitted_request", failure
    else:
        decision, next_action, denial_reason = "approve", "approve_submitted_request", None
    return {"card_tier":tier if rule else None, "errors":errors,
            "current_credit_limit":number(limit), "requested_increase_amount":number(requested),
            "maximum_increase_amount":number(maximum), "proposed_new_credit_limit":number(proposed),
            "requested_amount_exceeds_limit":exceeds, "can_submit":can_submit,
            "checks":checks, "decision":decision, "denial_reason":denial_reason,
            "next_action":next_action}

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(evaluate(payload), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error":str(exc)}))
        sys.exit(1)
