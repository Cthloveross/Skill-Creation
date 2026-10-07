#!/usr/bin/env python3
"""Evaluate normalized credit-limit-increase policy facts.

Reads one JSON object from stdin and writes one JSON object to stdout. No network,
filesystem, banking, or tool action is performed.

Input schema:
{
  "card_tier": "entry-tier" | "mid-tier" | "premium-tier",  # required;
      # Gold Rewards Card may instead be supplied as card_type.
  "card_type": "Gold Rewards Card",                              # optional
  "current_credit_limit": number|string,                          # currency accepted
  "requested_increase_amount": integer|numeric-string,            # whole dollars
  "account_open_date": "YYYY-MM-DD" | "MM/DD/YYYY",             # optional until post-check
  "as_of_date": "YYYY-MM-DD" | timestamp beginning YYYY-MM-DD,   # optional until post-check
  "last_approved_request_submitted_date": date|null,              # optional; prior approved only
  "utilization_percent": number|string|null,                      # optional if balance supplied
  "current_balance": number|string|null,                          # optional if utilization supplied
  "has_active_disputes": true|false|null,
  "has_pending_replacement": true|false|null,
  "is_current_no_past_due": true|false|null,
  "consecutive_on_time_months": integer|null
}

Output includes `can_submit` for the pre-submission gate, all individual check
states, and a final `decision` once all post-submission facts are known. Currency
fields in output are JSON numbers suitable for the approval tool's float argument.
"""

import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

POLICY = {
    "entry-tier": {"age": 120, "cooldown": 120, "util": Decimal("70"), "payments": 6, "maximum_fraction": Decimal("0.25")},
    "mid-tier": {"age": 90, "cooldown": 90, "util": Decimal("80"), "payments": 3, "maximum_fraction": Decimal("0.50")},
    "premium-tier": {"age": 60, "cooldown": 60, "util": Decimal("90"), "payments": 3, "maximum_fraction": Decimal("0.50")},
}

FAILURE_ORDER = [
    ("account_age", "insufficient_account_age"),
    ("cooldown", "cooldown_period_active"),
    ("active_disputes", "pending_disputes"),
    ("replacement_card", "pending_replacement_card"),
    ("good_standing", "past_due_balance"),
    ("utilization", "high_utilization"),
    ("payment_history", "insufficient_payment_history"),
]


def as_decimal(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        text = str(value).strip().replace("$", "").replace(",", "").replace("%", "")
        if not text:
            return None
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def as_date(value):
    if value is None:
        return None
    text = str(value).strip()
    for parser in (
        lambda: date.fromisoformat(text[:10]),
        lambda: datetime.strptime(text, "%m/%d/%Y").date(),
    ):
        try:
            return parser()
        except ValueError:
            pass
    return None


def state_from_boolean(value, failure_when_true=False):
    if value is None or not isinstance(value, bool):
        return "unknown"
    failed = value if failure_when_true else not value
    return "fail" if failed else "pass"


def money(value):
    """Convert Decimal to a JSON number without binary arithmetic during policy checks."""
    return float(value) if value is not None else None


def main(data):
    tier = data.get("card_tier")
    if tier is not None:
        tier = str(tier).strip().lower()
    if tier not in POLICY and data.get("card_type") == "Gold Rewards Card":
        tier = "premium-tier"

    errors = []
    if tier not in POLICY:
        errors.append("A supported, verified card tier is required.")
        policy = None
    else:
        policy = POLICY[tier]

    limit = as_decimal(data.get("current_credit_limit"))
    if limit is None or limit <= 0:
        errors.append("current_credit_limit must be a positive number.")

    requested = as_decimal(data.get("requested_increase_amount"))
    request_is_whole = requested is not None and requested == requested.to_integral_value()
    if requested is None or not request_is_whole or requested <= 0:
        errors.append("requested_increase_amount must be a positive whole-dollar amount.")

    maximum = limit * policy["maximum_fraction"] if limit is not None and policy else None
    proposed = limit + requested if limit is not None and requested is not None and request_is_whole and requested > 0 else None
    exceeds_maximum = maximum is not None and requested is not None and request_is_whole and requested > maximum
    can_submit = not errors and not exceeds_maximum

    checks = []

    opened = as_date(data.get("account_open_date"))
    as_of = as_date(data.get("as_of_date"))
    if policy and opened and as_of and as_of >= opened:
        age_days = (as_of - opened).days
        age_state = "pass" if age_days >= policy["age"] else "fail"
        age_eligible_date = opened + timedelta(days=policy["age"])
    else:
        age_days = None
        age_state = "unknown"
        age_eligible_date = None
    checks.append({"name": "account_age", "state": age_state, "age_days": age_days,
                   "minimum_days": policy["age"] if policy else None,
                   "eligible_on": age_eligible_date.isoformat() if age_eligible_date else None})

    prior = as_date(data.get("last_approved_request_submitted_date"))
    if policy and as_of:
        if prior is None:
            cooldown_state, cooldown_date = "pass", None
        else:
            cooldown_date = prior + timedelta(days=policy["cooldown"])
            cooldown_state = "pass" if as_of >= cooldown_date else "fail"
    else:
        cooldown_state, cooldown_date = "unknown", None
    checks.append({"name": "cooldown", "state": cooldown_state,
                   "prior_approved_submission_date": prior.isoformat() if prior else None,
                   "eligible_on": cooldown_date.isoformat() if cooldown_date else None,
                   "required_days": policy["cooldown"] if policy else None})

    dispute_state = state_from_boolean(data.get("has_active_disputes"), failure_when_true=True)
    checks.append({"name": "active_disputes", "state": dispute_state})
    replacement_state = state_from_boolean(data.get("has_pending_replacement"), failure_when_true=True)
    checks.append({"name": "replacement_card", "state": replacement_state})
    standing_state = state_from_boolean(data.get("is_current_no_past_due"), failure_when_true=False)
    checks.append({"name": "good_standing", "state": standing_state})

    utilization = as_decimal(data.get("utilization_percent"))
    if utilization is None:
        balance = as_decimal(data.get("current_balance"))
        if balance is not None and limit is not None and limit > 0:
            utilization = balance * Decimal("100") / limit
    if policy and utilization is not None and utilization >= 0:
        utilization_state = "pass" if utilization < policy["util"] else "fail"
    else:
        utilization_state = "unknown"
    checks.append({"name": "utilization", "state": utilization_state,
                   "utilization_percent": money(utilization),
                   "must_be_below_percent": money(policy["util"]) if policy else None})

    payment_months = data.get("consecutive_on_time_months")
    if isinstance(payment_months, bool):
        payment_months = None
    try:
        payment_months = int(payment_months) if payment_months is not None else None
    except (TypeError, ValueError):
        payment_months = None
    if policy and payment_months is not None and payment_months >= 0:
        payment_state = "pass" if payment_months >= policy["payments"] else "fail"
    else:
        payment_state = "unknown"
    checks.append({"name": "payment_history", "state": payment_state,
                   "consecutive_on_time_months": payment_months,
                   "required_months": policy["payments"] if policy else None})

    by_name = {item["name"]: item["state"] for item in checks}
    failure_reason = next((reason for name, reason in FAILURE_ORDER if by_name.get(name) == "fail"), None)
    any_unknown = any(item["state"] == "unknown" for item in checks)

    if not can_submit:
        decision = "do_not_submit"
        next_action = "ask_customer_to_adjust" if exceeds_maximum else "obtain_valid_pre_submission_facts"
        denial_reason = "requested_amount_exceeds_limit" if exceeds_maximum else None
    elif any_unknown:
        decision = "incomplete"
        next_action = "complete_required_eligibility_checks"
        denial_reason = None
    elif failure_reason:
        decision = "deny"
        next_action = "deny_submitted_request"
        denial_reason = failure_reason
    else:
        decision = "approve"
        next_action = "approve_submitted_request"
        denial_reason = None

    return {
        "card_tier": tier,
        "errors": errors,
        "requested_increase_amount": money(requested),
        "current_credit_limit": money(limit),
        "maximum_increase_amount": money(maximum),
        "proposed_new_credit_limit": money(proposed),
        "requested_amount_exceeds_limit": exceeds_maximum,
        "can_submit": can_submit,
        "checks": checks,
        "decision": decision,
        "denial_reason": denial_reason,
        "next_action": next_action,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(payload), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
