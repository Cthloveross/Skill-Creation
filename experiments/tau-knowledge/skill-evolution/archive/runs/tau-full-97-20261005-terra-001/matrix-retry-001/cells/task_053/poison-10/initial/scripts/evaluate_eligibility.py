#!/usr/bin/env python3
"""Deterministic eligibility calculations for the credit-card dispute/CLI Skill.

Read one JSON object from stdin and write one JSON object to stdout.  The caller is
responsible for obtaining live records and for performing all banking-tool actions.
"""
import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CLI_RULES = {
    "entry-tier": {"age_days": 120, "cooldown_days": 120, "utilization_lt": Decimal("70"), "payment_months": 6, "max_fraction": Decimal("0.25")},
    "mid-tier": {"age_days": 90, "cooldown_days": 90, "utilization_lt": Decimal("80"), "payment_months": 3, "max_fraction": Decimal("0.50")},
    "premium-tier": {"age_days": 60, "cooldown_days": 60, "utilization_lt": Decimal("90"), "payment_months": 3, "max_fraction": Decimal("0.50")},
}
PROVISIONAL_MAX = {
    "entry": Decimal("2500"),
    "mid": Decimal("5000"),
    "premium": Decimal("10000"),
    "elite": Decimal("15000"),
    "invitation": Decimal("25000"),
}
PROVISIONAL_REASONS = {
    "unauthorized_fraudulent_charge",
    "duplicate_charge",
    "goods_services_not_received",
}
ALL_REASONS = PROVISIONAL_REASONS | {
    "incorrect_amount",
    "goods_services_not_as_described",
    "canceled_subscription_still_charging",
    "refund_never_processed",
}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("date/timestamp is required")
    text = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError("unsupported date/timestamp format: " + text) from exc


def money(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(field + " must be a decimal number")
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(field + " must be a decimal number") from exc
    if not result.is_finite():
        raise ValueError(field + " must be finite")
    return result


def decimal_text(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def bool_state(value, field, errors):
    if value is True or value is False or value is None:
        return value
    errors.append(field + " must be true, false, or null")
    return None


def cli(data):
    errors = []
    tier = data.get("tier")
    if tier not in CLI_RULES:
        return {"operation": "cli", "errors": ["tier must be entry-tier, mid-tier, or premium-tier"]}
    rules = CLI_RULES[tier]
    try:
        current_limit = money(data.get("current_limit"), "current_limit")
        balance = money(data.get("current_balance"), "current_balance")
        increase = money(data.get("requested_increase"), "requested_increase")
        opened = parse_date(data.get("account_open_date"))
        today = parse_date(data.get("now"))
    except ValueError as exc:
        return {"operation": "cli", "errors": [str(exc)]}
    if current_limit <= 0:
        errors.append("current_limit must be greater than zero")
    if increase <= 0 or increase != increase.to_integral_value():
        errors.append("requested_increase must be a positive whole-dollar amount")
    if today < opened:
        errors.append("now cannot precede account_open_date")
    if errors:
        return {"operation": "cli", "errors": errors}

    approved = data.get("approved_request_times", [])
    if not isinstance(approved, list):
        return {"operation": "cli", "errors": ["approved_request_times must be an array"]}
    try:
        approved_dates = [parse_date(item) for item in approved]
    except ValueError as exc:
        return {"operation": "cli", "errors": ["approved_request_times: " + str(exc)]}
    if any(item > today for item in approved_dates):
        return {"operation": "cli", "errors": ["approved_request_times cannot contain a future date"]}

    maximum = current_limit * rules["max_fraction"]
    age_days = (today - opened).days
    utilization = (balance / current_limit) * Decimal("100")
    most_recent = max(approved_dates) if approved_dates else None
    elapsed = (today - most_recent).days if most_recent else None
    cooldown_ok = most_recent is None or elapsed >= rules["cooldown_days"]
    next_eligible = None if most_recent is None else most_recent.fromordinal(most_recent.toordinal() + rules["cooldown_days"]).isoformat()

    checks = {
        "amount_within_limit": increase <= maximum,
        "account_age": age_days >= rules["age_days"],
        "cooldown": cooldown_ok,
        "utilization": utilization < rules["utilization_lt"],
    }
    supplied = data.get("external_checks", {})
    if not isinstance(supplied, dict):
        return {"operation": "cli", "errors": ["external_checks must be an object"]}
    for field in ("pending_disputes_clear", "no_pending_replacement", "good_standing", "payment_history_sufficient"):
        checks[field] = bool_state(supplied.get(field), field, errors)
    if errors:
        return {"operation": "cli", "errors": errors}

    result = {
        "operation": "cli",
        "tier": tier,
        "maximum_increase": decimal_text(maximum),
        "requested_increase": decimal_text(increase),
        "new_credit_limit": decimal_text(current_limit + increase),
        "account_age_days": age_days,
        "utilization_percent": decimal_text(utilization),
        "minimum_account_age_days": rules["age_days"],
        "cooldown_days": rules["cooldown_days"],
        "utilization_must_be_below_percent": decimal_text(rules["utilization_lt"]),
        "payment_history_months_required": rules["payment_months"],
        "most_recent_approved_request_date": most_recent.isoformat() if most_recent else None,
        "next_eligible_date_if_cooldown_applies": next_eligible,
        "checks": checks,
    }
    if not checks["amount_within_limit"]:
        result.update({"pre_submission_action": "do_not_submit_requested_amount", "decision": "do_not_submit", "denial_reason": "requested_amount_exceeds_limit"})
        return result

    result["pre_submission_action"] = "submit_then_complete_all_eligibility_checks"
    unknown = [name for name, state in checks.items() if state is None]
    if unknown:
        result.update({"decision": "await_required_check", "unresolved_checks": unknown, "denial_reason": None})
        return result

    denial_order = [
        ("account_age", "insufficient_account_age"),
        ("cooldown", "cooldown_period_active"),
        ("pending_disputes_clear", "pending_disputes"),
        ("no_pending_replacement", "pending_replacement_card"),
        ("good_standing", "past_due_balance"),
        ("utilization", "high_utilization"),
        ("payment_history_sufficient", "insufficient_payment_history"),
    ]
    for check, reason in denial_order:
        if checks[check] is False:
            result.update({"decision": "deny", "denial_reason": reason})
            return result
    result.update({"decision": "approve", "denial_reason": None})
    return result


def provisional(data):
    errors = []
    tier = data.get("tier")
    if tier not in PROVISIONAL_MAX:
        return {"operation": "provisional", "errors": ["tier must be entry, mid, premium, elite, or invitation"]}
    reason = data.get("dispute_reason")
    if reason not in ALL_REASONS:
        errors.append("dispute_reason is not an allowed dispute reason")
    try:
        opened = parse_date(data.get("account_open_date"))
        today = parse_date(data.get("now"))
        purchase = parse_date(data.get("purchase_date"))
        amount = money(data.get("amount"), "amount")
    except ValueError as exc:
        return {"operation": "provisional", "errors": [str(exc)]}
    if today < opened or today < purchase:
        errors.append("now cannot precede account_open_date or purchase_date")
    count = data.get("disputes_last_12_months")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        errors.append("disputes_last_12_months must be a nonnegative integer")
    contacted = data.get("contacted_merchant")
    if contacted is not True and contacted is not False:
        errors.append("contacted_merchant must be true or false")
    if errors:
        return {"operation": "provisional", "errors": errors}

    age = (today - opened).days
    purchase_age = (today - purchase).days
    criteria = {
        "account_age_at_least_60_days": age >= 60,
        "eligible_reason": reason in PROVISIONAL_REASONS,
        "goods_not_received_purchase_more_than_30_days": (reason != "goods_services_not_received" or purchase_age > 30),
        "amount_at_least_25": amount >= Decimal("25"),
        "amount_within_tier_maximum": amount <= PROVISIONAL_MAX[tier],
        "no_more_than_two_disputes_last_12_months": count <= 2,
        "merchant_contact_requirement": reason == "unauthorized_fraudulent_charge" or contacted is True,
    }
    return {
        "operation": "provisional",
        "tier": tier,
        "account_age_days": age,
        "purchase_age_days": purchase_age,
        "tier_maximum": decimal_text(PROVISIONAL_MAX[tier]),
        "criteria": criteria,
        "eligible": all(criteria.values()),
        "errors": [],
    }


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"errors": ["invalid JSON: " + str(exc)]}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"errors": ["input must be a JSON object"]}))
        return
    operation = data.get("operation")
    if operation == "cli":
        result = cli(data)
    elif operation == "provisional":
        result = provisional(data)
    else:
        result = {"errors": ["operation must be cli or provisional"]}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
