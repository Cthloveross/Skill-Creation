#!/usr/bin/env python3
"""Deterministically validate and evaluate credit-limit-increase facts.

Input: one JSON object as documented by SKILL.md.
Output: one JSON object.  This program performs no external calls and no state changes.
"""

import json
import re
import sys
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_FLOOR


TIER_RULES = {
    "entry-tier": {
        "age_days": 120, "cooldown_days": 120, "utilization": Decimal("70"),
        "payment_months": 6, "maximum_fraction": Decimal("0.25"),
    },
    "mid-tier": {
        "age_days": 90, "cooldown_days": 90, "utilization": Decimal("80"),
        "payment_months": 3, "maximum_fraction": Decimal("0.50"),
    },
    "premium-tier": {
        "age_days": 60, "cooldown_days": 60, "utilization": Decimal("90"),
        "payment_months": 3, "maximum_fraction": Decimal("0.50"),
    },
}

# Only mappings supported by the supplied CLI material are included. Callers can
# always supply card_tier directly for other valid products.
CARD_TYPE_TIERS = {
    "bronze rewards card": "entry-tier",
    "ecocard": "entry-tier",
    "business bronze rewards card": "entry-tier",
}

FINAL_DISPUTE_STATUSES = {"closed", "resolved", "cancelled", "canceled", "denied"}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled", "canceled"}
GOOD_ACCOUNT_STATUSES = {"active", "current", "good_standing", "good standing"}
DENIAL_PRIORITY = [
    ("account_age", "insufficient_account_age"),
    ("cooldown", "cooldown_period_active"),
    ("disputes", "pending_disputes"),
    ("replacement_orders", "pending_replacement_card"),
    ("good_standing", "past_due_balance"),
    ("utilization", "high_utilization"),
    ("payment_history", "insufficient_payment_history"),
]


def decimal_value(value, field, errors):
    if isinstance(value, bool) or value is None:
        errors.append("%s must be a decimal amount" % field)
        return None
    try:
        result = Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        errors.append("%s must be a decimal amount" % field)
        return None
    if not result.is_finite():
        errors.append("%s must be finite" % field)
        return None
    return result


def resolve_tier(data, errors):
    tier = data.get("card_tier")
    if isinstance(tier, str) and tier.strip().lower() in TIER_RULES:
        return tier.strip().lower()
    card_type = data.get("card_type")
    if isinstance(card_type, str):
        mapped = CARD_TYPE_TIERS.get(card_type.strip().lower())
        if mapped:
            return mapped
    errors.append("provide a supported card_tier or a recognized documented card_type")
    return None


def amount_facts(data):
    errors = []
    tier = resolve_tier(data, errors)
    limit = decimal_value(data.get("current_credit_limit"), "current_credit_limit", errors)
    amount = data.get("requested_increase_amount")
    if isinstance(amount, bool) or not isinstance(amount, int):
        errors.append("requested_increase_amount must be a whole-dollar JSON integer")
        amount = None
    elif amount <= 0:
        errors.append("requested_increase_amount must be greater than zero")
    if errors:
        return None, errors
    max_amount = (limit * TIER_RULES[tier]["maximum_fraction"]).to_integral_value(rounding=ROUND_FLOOR)
    if Decimal(amount) > max_amount:
        return {
            "tier": tier,
            "valid_amount": False,
            "max_increase_amount": int(max_amount),
            "requested_increase_amount": amount,
            "current_credit_limit": float(limit),
        }, []
    return {
        "tier": tier,
        "valid_amount": True,
        "max_increase_amount": int(max_amount),
        "requested_increase_amount": amount,
        "current_credit_limit": float(limit),
        "new_credit_limit": float(limit + Decimal(amount)),
    }, []


def parse_time(value):
    """Accept ISO-like values, MM/DD/YYYY, and timestamps ending in a TZ label."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    # The evaluation clock may use a trailing abbreviation such as EST.  The
    # local calendar/time remains useful even when Python cannot parse the label.
    text = re.sub(r"\s+[A-Za-z]{2,5}$", "", text)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def check(name, passed, detail, **extra):
    result = {"name": name, "passed": passed, "detail": detail}
    result.update(extra)
    return result


def evaluate(data, amount):
    rules = TIER_RULES[amount["tier"]]
    missing = []
    checks = []

    now = parse_time(data.get("current_time"))
    opened = parse_time(data.get("account_open_date"))
    if now is None or opened is None or now.date() < opened.date():
        missing.append("current_time and a valid account_open_date")
        checks.append(check("account_age", None, "Account age could not be calculated."))
    else:
        age_days = (now.date() - opened.date()).days
        checks.append(check("account_age", age_days >= rules["age_days"], "Account age is %d days; minimum is %d." % (age_days, rules["age_days"]), age_days=age_days, required_days=rules["age_days"]))

    if "most_recent_approved_request_at" not in data:
        missing.append("most_recent_approved_request_at derived from CLI history")
        checks.append(check("cooldown", None, "Approved CLI history was not provided."))
    elif data.get("most_recent_approved_request_at") is None:
        checks.append(check("cooldown", True, "No prior approved CLI request was reported."))
    else:
        recent = parse_time(data.get("most_recent_approved_request_at"))
        if now is None or recent is None:
            missing.append("valid current_time and most_recent_approved_request_at")
            checks.append(check("cooldown", None, "Cooldown could not be calculated."))
        else:
            eligible_at = recent + timedelta(days=rules["cooldown_days"])
            passed = now >= eligible_at
            checks.append(check("cooldown", passed, "Cooldown ends at %s." % eligible_at.isoformat(sep=" "), eligible_on=eligible_at.isoformat(sep=" "), required_days=rules["cooldown_days"]))

    disputes = data.get("disputes")
    if not isinstance(disputes, list):
        missing.append("disputes array from dispute-history lookup")
        checks.append(check("disputes", None, "Dispute lookup was not provided."))
    else:
        active = []
        for item in disputes:
            status = item.get("status") if isinstance(item, dict) else None
            normalized = status.strip().lower() if isinstance(status, str) else "unknown"
            if normalized not in FINAL_DISPUTE_STATUSES:
                active.append(normalized)
        checks.append(check("disputes", not active, "No active disputes found." if not active else "Active or non-final disputes found.", active_statuses=active))

    orders = data.get("replacement_orders")
    if not isinstance(orders, list):
        missing.append("replacement_orders array from replacement-order lookup")
        checks.append(check("replacement_orders", None, "Replacement-order lookup was not provided."))
    else:
        pending = []
        for item in orders:
            status = item.get("status") if isinstance(item, dict) else None
            normalized = status.strip().lower() if isinstance(status, str) else "unknown"
            if normalized not in FINAL_REPLACEMENT_STATUSES:
                pending.append(normalized)
        checks.append(check("replacement_orders", not pending, "No pending replacement orders found." if not pending else "Pending or non-final replacement orders found.", blocking_statuses=pending))

    balance = decimal_value(data.get("current_balance"), "current_balance", missing)
    limit = decimal_value(data.get("current_credit_limit"), "current_credit_limit", missing)
    past_due = decimal_value(data.get("past_due_amount"), "past_due_amount", missing)
    status = data.get("account_status")
    if balance is None or limit is None or past_due is None or not isinstance(status, str):
        checks.append(check("good_standing", None, "Account status, balance, or past-due amount was not verified."))
    else:
        status_ok = status.strip().lower() in GOOD_ACCOUNT_STATUSES
        standing = status_ok and past_due <= 0
        checks.append(check("good_standing", standing, "Account must be current and have no past-due balance.", account_status=status, past_due_amount=float(past_due)))

    if balance is None or limit is None or limit <= 0:
        if limit is not None and limit <= 0:
            missing.append("positive current_credit_limit")
        checks.append(check("utilization", None, "Utilization could not be calculated."))
    else:
        utilization = balance / limit * Decimal("100")
        checks.append(check("utilization", utilization < rules["utilization"], "Utilization is %s%%; it must be below %s%%." % (utilization, rules["utilization"]), utilization_percent=float(utilization), maximum_exclusive_percent=float(rules["utilization"])))

    months = data.get("consecutive_on_time_months")
    if isinstance(months, bool) or not isinstance(months, int) or months < 0:
        missing.append("consecutive_on_time_months derived from payment history")
        checks.append(check("payment_history", None, "Payment-history result was not provided."))
    else:
        checks.append(check("payment_history", months >= rules["payment_months"], "Consecutive on-time months: %d; required: %d." % (months, rules["payment_months"]), consecutive_on_time_months=months, required_months=rules["payment_months"]))

    if missing:
        return {
            "valid_amount": True,
            "complete": False,
            "eligible": False,
            "action": "obtain_missing_verification",
            "missing_verification": sorted(set(missing)),
            "checks": checks,
        }

    failed = {item["name"] for item in checks if item["passed"] is False}
    if not failed:
        return {
            "valid_amount": True,
            "complete": True,
            "eligible": True,
            "action": "approve",
            "new_credit_limit": amount["new_credit_limit"],
            "checks": checks,
        }
    reason = next(reason for name, reason in DENIAL_PRIORITY if name in failed)
    return {
        "valid_amount": True,
        "complete": True,
        "eligible": False,
        "action": "deny",
        "denial_reason": reason,
        "failed_checks": [item["name"] for item in checks if item["passed"] is False],
        "checks": checks,
    }


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "errors": ["invalid JSON input: %s" % exc]}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"ok": False, "errors": ["input must be a JSON object"]}))
        return

    mode = data.get("mode")
    if mode not in ("preflight", "evaluate"):
        print(json.dumps({"ok": False, "errors": ["mode must be preflight or evaluate"]}))
        return
    amount, errors = amount_facts(data)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}))
        return
    if not amount["valid_amount"]:
        amount["ok"] = True
        amount["action"] = "request_corrected_amount"
        amount["errors"] = ["requested increase exceeds the tier maximum"]
        print(json.dumps(amount, sort_keys=True))
        return
    if mode == "preflight":
        amount["ok"] = True
        amount["action"] = "submit_request"
        print(json.dumps(amount, sort_keys=True))
        return

    result = evaluate(data, amount)
    result["ok"] = True
    result["tier"] = amount["tier"]
    result["requested_increase_amount"] = amount["requested_increase_amount"]
    result["max_increase_amount"] = amount["max_increase_amount"]
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
