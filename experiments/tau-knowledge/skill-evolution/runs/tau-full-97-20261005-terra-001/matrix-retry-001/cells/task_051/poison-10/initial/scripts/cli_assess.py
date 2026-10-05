#!/usr/bin/env python3
"""Deterministic CLI preflight and post-submission eligibility assessment.

Reads one JSON object from stdin and writes one JSON object to stdout.  This
program does not call bank tools and does not submit, approve, or deny requests.
"""
import json
import math
import sys
from datetime import date, datetime, timedelta

RULES = {
    "entry": {"age_days": 120, "cooldown_days": 120, "utilization_pct": 70.0,
              "max_fraction": 0.25, "payment_months": 6},
    "mid": {"age_days": 90, "cooldown_days": 90, "utilization_pct": 80.0,
            "max_fraction": 0.50, "payment_months": 3},
    "premium": {"age_days": 60, "cooldown_days": 60, "utilization_pct": 90.0,
                "max_fraction": 0.50, "payment_months": 3},
}


def parse_date(value, field, errors):
    if not isinstance(value, str):
        errors.append(f"{field} must be a YYYY-MM-DD string")
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        errors.append(f"{field} is not a valid YYYY-MM-DD date")
        return None


def number(value, field, errors):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{field} must be numeric")
        return None
    if not math.isfinite(float(value)):
        errors.append(f"{field} must be finite")
        return None
    return float(value)


def result(name, status, detail, **extra):
    item = {"name": name, "status": status, "detail": detail}
    item.update(extra)
    return item


def assess(payload):
    errors = []
    if not isinstance(payload, dict):
        return {"valid": False, "errors": ["input must be a JSON object"]}

    today = parse_date(payload.get("current_date"), "current_date", errors)
    account = payload.get("account")
    if not isinstance(account, dict):
        errors.append("account must be an object")
        account = {}
    tier = account.get("tier")
    if tier not in RULES:
        errors.append("account.tier must be entry, mid, or premium")
        rule = None
    else:
        rule = RULES[tier]

    limit = number(account.get("current_credit_limit"), "account.current_credit_limit", errors)
    balance = number(account.get("current_balance"), "account.current_balance", errors)
    requested_raw = payload.get("requested_increase_amount")
    requested = number(requested_raw, "requested_increase_amount", errors)
    if requested is not None and (requested <= 0 or not requested.is_integer()):
        errors.append("requested_increase_amount must be a positive whole-dollar amount")

    submitted = payload.get("request_submitted", False)
    if not isinstance(submitted, bool):
        errors.append("request_submitted must be Boolean")

    if errors:
        return {"valid": False, "errors": errors, "checks": [],
                "decision": {"action": "hold", "reason": "invalid_input"}}

    if limit <= 0:
        return {"valid": False, "errors": ["current_credit_limit must be greater than zero"],
                "checks": [], "decision": {"action": "hold", "reason": "invalid_input"}}
    if balance < 0:
        return {"valid": False, "errors": ["current_balance cannot be negative"],
                "checks": [], "decision": {"action": "hold", "reason": "invalid_input"}}

    max_amount = limit * rule["max_fraction"]
    max_integer = math.floor(max_amount + 1e-9)
    amount_allowed = requested <= max_amount + 1e-9
    pre_submission = {
        "tier": tier,
        "maximum_increase_amount": round(max_amount, 2),
        "maximum_requestable_integer_amount": max_integer,
        "requested_amount_valid": amount_allowed,
        "new_credit_limit": round(limit + requested, 2),
        "action": "may_submit" if amount_allowed else "ask_customer_to_adjust",
    }

    if not amount_allowed and not submitted:
        return {
            "valid": True, "errors": [], "pre_submission": pre_submission,
            "checks": [], "all_checks_observed": False,
            "decision": {"action": "ask_customer_to_adjust", "denial_reason": None,
                         "detail": "Requested increase exceeds the tier maximum; do not submit."},
        }
    if not submitted:
        return {
            "valid": True, "errors": [], "pre_submission": pre_submission,
            "checks": [], "all_checks_observed": False,
            "decision": {"action": "submit_required", "denial_reason": None,
                         "detail": "Amount is within the tier maximum; submit before eligibility checks."},
        }
    if not amount_allowed:
        return {
            "valid": True, "errors": [], "pre_submission": pre_submission,
            "checks": [], "all_checks_observed": True,
            "decision": {"action": "deny", "denial_reason": "requested_amount_exceeds_limit",
                         "detail": "An already-submitted request exceeds the tier maximum."},
        }

    post = payload.get("post_checks")
    if not isinstance(post, dict):
        return {
            "valid": True, "errors": ["post_checks is required after request submission"],
            "pre_submission": pre_submission, "checks": [], "all_checks_observed": False,
            "decision": {"action": "hold", "denial_reason": None,
                         "detail": "Post-submission eligibility evidence is missing."},
        }

    checks = []
    open_date = parse_date(post.get("account_open_date"), "post_checks.account_open_date", errors)
    if open_date is None or today is None:
        checks.append(result("account_age", "unknown", "Account opening date or current date is invalid."))
    elif open_date > today:
        checks.append(result("account_age", "unknown", "Account opening date is in the future."))
    else:
        age = (today - open_date).days
        checks.append(result("account_age", "pass" if age >= rule["age_days"] else "fail",
                             f"Account age is {age} days; requires at least {rule['age_days']}.",
                             age_days=age, required_days=rule["age_days"]))

    approved_dates = post.get("approved_submission_dates")
    if not isinstance(approved_dates, list):
        checks.append(result("cooldown", "unknown", "Approved request history is missing."))
    else:
        parsed = [parse_date(v, "post_checks.approved_submission_dates[]", errors) for v in approved_dates]
        if any(v is None for v in parsed) or today is None:
            checks.append(result("cooldown", "unknown", "Approved request history has an invalid date."))
        elif not parsed:
            checks.append(result("cooldown", "pass", "No prior approved CLI request was supplied."))
        else:
            latest = max(parsed)
            eligible_on = latest + timedelta(days=rule["cooldown_days"])
            status = "pass" if today >= eligible_on else "fail"
            checks.append(result("cooldown", status,
                                 f"Latest approved request was {latest.isoformat()}; eligible on {eligible_on.isoformat()}.",
                                 eligible_on=eligible_on.isoformat()))

    def nonnegative_count(key, name, reason):
        value = post.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            checks.append(result(name, "unknown", f"{key} is missing or invalid."))
        elif value == 0:
            checks.append(result(name, "pass", "None reported."))
        else:
            checks.append(result(name, "fail", f"{value} reported.", denial_reason=reason))

    nonnegative_count("active_disputes_count", "pending_disputes", "pending_disputes")
    nonnegative_count("pending_replacement_orders_count", "pending_replacement_card", "pending_replacement_card")

    current = post.get("account_current")
    due = number(post.get("past_due_amount"), "post_checks.past_due_amount", errors)
    if not isinstance(current, bool) or due is None or due < 0:
        checks.append(result("good_standing", "unknown", "Current-status or past-due evidence is invalid."))
    elif current and due == 0:
        checks.append(result("good_standing", "pass", "Account is current with no past-due balance."))
    else:
        checks.append(result("good_standing", "fail", "Account is not current or has a past-due balance.",
                             denial_reason="past_due_balance"))

    utilization = balance / limit * 100.0
    util_status = "pass" if utilization < rule["utilization_pct"] else "fail"
    checks.append(result("utilization", util_status,
                         f"Utilization is {utilization:.4f}%; must be below {rule['utilization_pct']:.0f}%.",
                         utilization_percent=round(utilization, 4), threshold_percent=rule["utilization_pct"],
                         denial_reason=None if util_status == "pass" else "high_utilization"))

    payments = post.get("recent_payment_months")
    required = rule["payment_months"]
    if not isinstance(payments, list) or any(not isinstance(v, bool) for v in payments):
        checks.append(result("payment_history", "unknown", "Recent payment-month results are missing or invalid."))
    elif len(payments) < required:
        checks.append(result("payment_history", "fail", f"Only {len(payments)} documented months; requires {required}.",
                             denial_reason="insufficient_payment_history"))
    elif all(payments[:required]):
        checks.append(result("payment_history", "pass", f"Most recent {required} months are consecutive on-time payments."))
    else:
        checks.append(result("payment_history", "fail", f"Most recent {required} months are not all on time.",
                             denial_reason="insufficient_payment_history"))

    unknown = [c for c in checks if c["status"] == "unknown"]
    failed = {c["name"] for c in checks if c["status"] == "fail"}
    reason_by_check = {
        "account_age": "insufficient_account_age", "cooldown": "cooldown_period_active",
        "pending_disputes": "pending_disputes", "pending_replacement_card": "pending_replacement_card",
        "good_standing": "past_due_balance", "utilization": "high_utilization",
        "payment_history": "insufficient_payment_history",
    }
    priority = ["account_age", "cooldown", "pending_disputes", "pending_replacement_card",
                "good_standing", "utilization", "payment_history"]
    if unknown:
        decision = {"action": "hold", "denial_reason": None,
                    "detail": "At least one required eligibility check is unresolved."}
    elif failed:
        primary = next(name for name in priority if name in failed)
        decision = {"action": "deny", "denial_reason": reason_by_check[primary],
                    "detail": f"Eligibility failed: {primary}."}
    else:
        decision = {"action": "approve", "denial_reason": None,
                    "new_credit_limit": round(limit + requested, 2),
                    "detail": "All required post-submission eligibility checks passed."}

    return {"valid": not errors, "errors": errors, "pre_submission": pre_submission,
            "checks": checks, "all_checks_observed": not bool(unknown), "decision": decision}


def main():
    try:
        payload = json.load(sys.stdin)
        output = assess(payload)
    except json.JSONDecodeError as exc:
        output = {"valid": False, "errors": [f"invalid JSON: {exc.msg}"], "checks": [],
                  "decision": {"action": "hold", "reason": "invalid_input"}}
    except Exception as exc:  # Preserve a machine-readable safe failure mode.
        output = {"valid": False, "errors": [f"assessment error: {type(exc).__name__}"], "checks": [],
                  "decision": {"action": "hold", "reason": "assessment_error"}}
    json.dump(output, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
