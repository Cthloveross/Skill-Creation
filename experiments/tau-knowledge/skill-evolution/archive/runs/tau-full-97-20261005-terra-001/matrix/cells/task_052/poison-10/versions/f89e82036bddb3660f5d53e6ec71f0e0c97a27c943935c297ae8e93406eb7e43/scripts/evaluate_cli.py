#!/usr/bin/env python3
"""Deterministic CLI amount and eligibility evaluator.

Input is one JSON object.  Modes:
  precheck: tier, current_credit_limit, and exactly one of
            requested_increase_amount (whole dollars) or requested_percent
            (10 means ten percent).
  decision: tier, current_credit_limit, current_balance, requested_increase_amount,
            account_open_date, as_of_date, last_approved_request_submitted_at
            (string or null), has_pending_disputes, has_pending_replacement_card,
            payment_history_sufficient, past_due_amount, and account_status.

All monetary inputs may be JSON numbers or decimal strings. Dates may be YYYY-MM-DD,
MM/DD/YYYY, or timestamps beginning with either date form. Output is JSON only.
"""
import json
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

RULES = {
    "entry": {"age": 120, "cooldown": 120, "utilization": Decimal("0.70"),
              "increase_fraction": Decimal("0.25"), "months": 6},
    "mid": {"age": 90, "cooldown": 90, "utilization": Decimal("0.80"),
            "increase_fraction": Decimal("0.50"), "months": 3},
    "premium": {"age": 60, "cooldown": 60, "utilization": Decimal("0.90"),
                "increase_fraction": Decimal("0.50"), "months": 3},
}


def fail(message):
    return {"ok": False, "error": message}


def money(value, field):
    if isinstance(value, bool):
        raise ValueError(field + " must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(field + " must be a valid decimal")
    if not result.is_finite():
        raise ValueError(field + " must be finite")
    return result


def parse_date(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(field + " is required")
    text = value.strip()
    candidates = [text[:10], text[:19]]
    for candidate in candidates:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    raise ValueError(field + " must begin with YYYY-MM-DD or MM/DD/YYYY")


def tier_rule(data):
    tier = data.get("tier")
    if not isinstance(tier, str) or tier.lower() not in RULES:
        raise ValueError("tier must be entry, mid, or premium")
    return tier.lower(), RULES[tier.lower()]


def dollar_string(value):
    return format(value.quantize(Decimal("0.01")), "f")


def precheck(data):
    tier, rule = tier_rule(data)
    limit = money(data.get("current_credit_limit"), "current_credit_limit")
    if limit <= 0:
        raise ValueError("current_credit_limit must be greater than zero")
    has_amount = "requested_increase_amount" in data
    has_percent = "requested_percent" in data
    if has_amount == has_percent:
        raise ValueError("provide exactly one of requested_increase_amount or requested_percent")
    if has_amount:
        amount = money(data["requested_increase_amount"], "requested_increase_amount")
        if amount != amount.to_integral_value():
            raise ValueError("requested_increase_amount must be a whole-dollar integer")
    else:
        percent = money(data["requested_percent"], "requested_percent")
        if percent <= 0:
            raise ValueError("requested_percent must be greater than zero")
        amount = limit * percent / Decimal("100")
        if amount != amount.to_integral_value():
            return {
                "ok": True, "decision": "do_not_submit", "submit_allowed": False,
                "reason": "percentage_does_not_produce_whole_dollar_amount",
                "maximum_whole_dollar_increase": int((limit * rule["increase_fraction"]).to_integral_value(rounding=ROUND_FLOOR)),
                "message": "Ask the customer for a whole-dollar increase; do not round automatically."
            }
    cap_exact = limit * rule["increase_fraction"]
    cap_whole = int(cap_exact.to_integral_value(rounding=ROUND_FLOOR))
    allowed = amount > 0 and amount <= cap_exact
    result = {
        "ok": True,
        "tier": tier,
        "requested_increase_amount": int(amount),
        "maximum_whole_dollar_increase": cap_whole,
        "new_credit_limit": dollar_string(limit + amount),
        "submit_allowed": bool(allowed),
    }
    if allowed:
        result["decision"] = "ready_to_submit"
    else:
        result.update({
            "decision": "do_not_submit",
            "reason": "requested_amount_exceeds_limit" if amount > cap_exact else "requested_amount_must_be_positive",
            "message": "Do not submit or deny; request a valid revised amount."
        })
    return result


def decision(data):
    tier, rule = tier_rule(data)
    required = ["current_credit_limit", "current_balance", "requested_increase_amount",
                "account_open_date", "as_of_date", "has_pending_disputes",
                "has_pending_replacement_card", "payment_history_sufficient",
                "past_due_amount", "account_status", "last_approved_request_submitted_at"]
    missing = [key for key in required if key not in data]
    if missing:
        return {"ok": True, "decision": "incomplete", "checks_complete": False,
                "missing_fields": missing}
    bool_fields = ["has_pending_disputes", "has_pending_replacement_card", "payment_history_sufficient"]
    bad_bools = [key for key in bool_fields if not isinstance(data[key], bool)]
    if bad_bools:
        return {"ok": True, "decision": "incomplete", "checks_complete": False,
                "error": "Boolean findings required", "invalid_fields": bad_bools}
    limit = money(data["current_credit_limit"], "current_credit_limit")
    balance = money(data["current_balance"], "current_balance")
    past_due = money(data["past_due_amount"], "past_due_amount")
    amount = money(data["requested_increase_amount"], "requested_increase_amount")
    if limit <= 0 or balance < 0 or past_due < 0 or amount <= 0 or amount != amount.to_integral_value():
        return {"ok": True, "decision": "incomplete", "checks_complete": False,
                "error": "Invalid monetary findings"}
    try:
        opened = parse_date(data["account_open_date"], "account_open_date")
        now = parse_date(data["as_of_date"], "as_of_date")
    except ValueError as exc:
        return {"ok": True, "decision": "incomplete", "checks_complete": False, "error": str(exc)}
    if now < opened:
        return {"ok": True, "decision": "incomplete", "checks_complete": False,
                "error": "as_of_date precedes account_open_date"}
    prior = data["last_approved_request_submitted_at"]
    cooldown_elapsed = None
    next_eligible = None
    if prior is not None:
        try:
            prior_date = parse_date(prior, "last_approved_request_submitted_at")
        except ValueError as exc:
            return {"ok": True, "decision": "incomplete", "checks_complete": False, "error": str(exc)}
        if prior_date > now:
            return {"ok": True, "decision": "incomplete", "checks_complete": False,
                    "error": "prior approved request is in the future"}
        cooldown_elapsed = (now - prior_date).days
        next_eligible = (prior_date + timedelta(days=rule["cooldown"])).isoformat()
    utilization = balance / limit
    account_age = (now - opened).days
    amount_valid = amount <= limit * rule["increase_fraction"]
    status_active = str(data["account_status"]).upper() == "ACTIVE"
    checks = {
        "account_age": account_age >= rule["age"],
        "cooldown": prior is None or cooldown_elapsed >= rule["cooldown"],
        "pending_disputes": not data["has_pending_disputes"],
        "pending_replacement_card": not data["has_pending_replacement_card"],
        "account_good_standing": past_due == 0 and status_active,
        "utilization": utilization < rule["utilization"],
        "payment_history": data["payment_history_sufficient"],
    }
    failures = []
    if not amount_valid:
        # This should have been stopped before submission, so do not recommend an API denial.
        return {"ok": True, "decision": "do_not_submit", "checks_complete": True,
                "error": "Invalid amount was supplied to post-submission evaluation",
                "primary_denial_reason": "requested_amount_exceeds_limit"}
    ordered = [
        ("account_age", "insufficient_account_age"),
        ("cooldown", "cooldown_period_active"),
        ("pending_disputes", "pending_disputes"),
        ("pending_replacement_card", "pending_replacement_card"),
        ("account_good_standing", "past_due_balance" if past_due > 0 else "other"),
        ("utilization", "high_utilization"),
        ("payment_history", "insufficient_payment_history"),
    ]
    for key, reason in ordered:
        if not checks[key]:
            failures.append({"check": key, "denial_reason": reason})
    output = {
        "ok": True, "checks_complete": True, "tier": tier,
        "account_age_days": account_age,
        "utilization_percent": float(utilization * Decimal("100")),
        "required_payment_months": rule["months"],
        "next_eligible_date": next_eligible,
        "check_results": checks,
        "new_credit_limit": dollar_string(limit + amount),
        "all_failures": failures,
    }
    if failures:
        output.update({"decision": "deny", "primary_denial_reason": failures[0]["denial_reason"]})
    else:
        output.update({"decision": "approve", "primary_denial_reason": None})
    return output


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        mode = data.get("mode")
        if mode == "precheck":
            result = precheck(data)
        elif mode == "decision":
            result = decision(data)
        else:
            result = fail("mode must be precheck or decision")
    except (ValueError, TypeError, KeyError) as exc:
        result = fail(str(exc))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
