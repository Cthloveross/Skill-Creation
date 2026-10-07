#!/usr/bin/env python3
"""Deterministic CLI and provisional-credit evaluation.

Reads one JSON object from stdin and emits one JSON object to stdout. This helper
performs no lookup, banking action, or decision recording; callers must obtain and
validate all live facts and invoke required banking tools themselves.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CLI = {
    "entry-tier": (120, 120, Decimal("70"), 6, Decimal("0.25")),
    "mid-tier": (90, 90, Decimal("80"), 3, Decimal("0.50")),
    "premium-tier": (60, 60, Decimal("90"), 3, Decimal("0.50")),
}
PROVISIONAL_MAX = {
    "entry": Decimal("2500"), "mid": Decimal("5000"),
    "premium": Decimal("10000"), "elite": Decimal("15000"),
    "invitation": Decimal("25000"),
}
REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
PROVISIONAL_REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"
}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("date/timestamp is required")
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError("unsupported date/timestamp format: " + value) from exc


def money(value, field):
    if value is None or isinstance(value, bool):
        raise ValueError(field + " must be a finite decimal number")
    try:
        amount = Decimal(str(value).strip().replace("$", "").replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(field + " must be a finite decimal number") from exc
    if not amount.is_finite():
        raise ValueError(field + " must be a finite decimal number")
    return amount


def display(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def cli(data):
    tier = data.get("tier")
    if tier not in CLI:
        return {"operation": "cli", "errors": ["tier must be entry-tier, mid-tier, or premium-tier"]}
    try:
        limit = money(data.get("current_limit"), "current_limit")
        balance = money(data.get("current_balance"), "current_balance")
        increase = money(data.get("requested_increase"), "requested_increase")
        opened = parse_date(data.get("account_open_date"))
        today = parse_date(data.get("now"))
    except ValueError as exc:
        return {"operation": "cli", "errors": [str(exc)]}
    if limit <= 0 or increase <= 0 or increase != increase.to_integral_value() or today < opened:
        return {"operation": "cli", "errors": ["limit must be positive, increase a positive whole dollar, and dates chronological"]}

    approved = data.get("approved_request_times", [])
    if not isinstance(approved, list):
        return {"operation": "cli", "errors": ["approved_request_times must be an array"]}
    try:
        prior = [parse_date(item) for item in approved]
    except ValueError as exc:
        return {"operation": "cli", "errors": ["approved_request_times: " + str(exc)]}
    if any(item > today for item in prior):
        return {"operation": "cli", "errors": ["approved_request_times cannot include a future date"]}

    age_required, cooldown_days, util_ceiling, months, fraction = CLI[tier]
    maximum = limit * fraction
    utilization = balance / limit * Decimal("100")
    recent = max(prior) if prior else None
    cooldown_ok = recent is None or (today - recent).days >= cooldown_days

    external = data.get("external_checks", {})
    if not isinstance(external, dict):
        return {"operation": "cli", "errors": ["external_checks must be an object"]}
    names = (
        "pending_disputes_clear", "no_pending_replacement",
        "good_standing", "payment_history_sufficient",
    )
    if any(external.get(name) not in (True, False, None) for name in names):
        return {"operation": "cli", "errors": ["external check values must be true, false, or null"]}

    checks = {
        "amount_within_limit": increase <= maximum,
        "account_age": (today - opened).days >= age_required,
        "cooldown": cooldown_ok,
        "utilization": utilization < util_ceiling,
        **{name: external.get(name) for name in names},
    }
    result = {
        "operation": "cli",
        "tier": tier,
        "errors": [],
        "maximum_increase": display(maximum),
        "requested_increase": display(increase),
        "new_credit_limit": display(limit + increase),
        "account_age_days": (today - opened).days,
        "utilization_percent": display(utilization),
        "minimum_account_age_days": age_required,
        "cooldown_days": cooldown_days,
        "utilization_must_be_below_percent": display(util_ceiling),
        "payment_history_months_required": months,
        "checks": checks,
        "most_recent_approved_request_date": recent.isoformat() if recent else None,
        "next_eligible_date_if_cooldown_applies": (
            recent.fromordinal(recent.toordinal() + cooldown_days).isoformat() if recent else None
        ),
    }
    if not checks["amount_within_limit"]:
        result.update(
            pre_submission_action="do_not_submit_requested_amount",
            decision="do_not_submit",
            denial_reason="requested_amount_exceeds_limit",
        )
        return result

    result["pre_submission_action"] = "submit_then_complete_all_eligibility_checks"
    unknown = [name for name, state in checks.items() if state is None]
    if unknown:
        result.update(decision="await_required_check", denial_reason=None, unresolved_checks=unknown)
        return result

    denial_order = (
        ("account_age", "insufficient_account_age"),
        ("cooldown", "cooldown_period_active"),
        ("pending_disputes_clear", "pending_disputes"),
        ("no_pending_replacement", "pending_replacement_card"),
        ("good_standing", "past_due_balance"),
        ("utilization", "high_utilization"),
        ("payment_history_sufficient", "insufficient_payment_history"),
    )
    for field, reason in denial_order:
        if not checks[field]:
            result.update(decision="deny", denial_reason=reason)
            return result
    result.update(decision="approve", denial_reason=None)
    return result


def provisional(data):
    tier = data.get("tier")
    reason = data.get("dispute_reason")
    if tier not in PROVISIONAL_MAX or reason not in REASONS:
        return {"operation": "provisional", "errors": ["invalid tier or dispute_reason"]}
    try:
        opened = parse_date(data.get("account_open_date"))
        today = parse_date(data.get("now"))
        purchase = parse_date(data.get("purchase_date"))
        amount = money(data.get("amount"), "amount")
    except ValueError as exc:
        return {"operation": "provisional", "errors": [str(exc)]}

    count = data.get("disputes_last_12_months")
    contacted = data.get("contacted_merchant")
    if (
        today < opened
        or today < purchase
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count < 0
        or contacted not in (True, False)
    ):
        return {"operation": "provisional", "errors": ["invalid dates, dispute count, or merchant-contact value"]}

    criteria = {
        "account_age_at_least_60_days": (today - opened).days >= 60,
        "eligible_reason": reason in PROVISIONAL_REASONS,
        "goods_not_received_purchase_more_than_30_days": (
            reason != "goods_services_not_received" or (today - purchase).days > 30
        ),
        "amount_at_least_25": amount >= Decimal("25"),
        "amount_within_tier_maximum": amount <= PROVISIONAL_MAX[tier],
        "no_more_than_two_disputes_last_12_months": count <= 2,
        "merchant_contact_requirement": (
            reason == "unauthorized_fraudulent_charge" or contacted is True
        ),
    }
    return {
        "operation": "provisional",
        "tier": tier,
        "errors": [],
        "criteria": criteria,
        "eligible": all(criteria.values()),
        "account_age_days": (today - opened).days,
        "purchase_age_days": (today - purchase).days,
        "tier_maximum": display(PROVISIONAL_MAX[tier]),
    }


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        if data.get("operation") == "cli":
            result = cli(data)
        elif data.get("operation") == "provisional":
            result = provisional(data)
        else:
            result = {"errors": ["operation must be cli or provisional"]}
    except (json.JSONDecodeError, ValueError) as exc:
        result = {"errors": [str(exc)]}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
