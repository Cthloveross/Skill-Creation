#!/usr/bin/env python3
"""Deterministic eligibility arithmetic for the credit-card workflow.

Reads one JSON object from stdin and writes one JSON object to stdout.
See SKILL.md for the two supported input schemas.
"""
import json
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation

CLI_RULES = {
    "entry": {"age_days": 120, "cooldown_days": 120, "utilization_lt": Decimal("70"), "on_time_months": 6, "max_fraction": Decimal("0.25")},
    "mid": {"age_days": 90, "cooldown_days": 90, "utilization_lt": Decimal("80"), "on_time_months": 3, "max_fraction": Decimal("0.50")},
    "premium": {"age_days": 60, "cooldown_days": 60, "utilization_lt": Decimal("90"), "on_time_months": 3, "max_fraction": Decimal("0.50")},
}
PROVISIONAL_CAPS = {
    "entry": Decimal("2500"),
    "mid": Decimal("5000"),
    "premium": Decimal("10000"),
    "elite": Decimal("15000"),
    "invitation": Decimal("25000"),
}


def parse_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    text = str(value)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError("dates must be YYYY-MM-DD or MM/DD/YYYY")


def decimal(value, field):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(field + " must be a decimal number")


def emit(value):
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def provisional(data):
    missing = []
    tier = data.get("tier")
    if tier not in PROVISIONAL_CAPS:
        missing.append("tier (entry, mid, premium, elite, or invitation)")
    opened = parse_date(data.get("account_open_date")) if data.get("account_open_date") else None
    today = parse_date(data.get("current_date")) if data.get("current_date") else None
    purchased = parse_date(data.get("purchase_date")) if data.get("purchase_date") else None
    amount = decimal(data.get("amount"), "amount")
    reason = data.get("reason")
    previous = data.get("prior_disputes_12m")
    contacted = data.get("contacted_merchant")
    for field, value in (("account_open_date", opened), ("current_date", today), ("purchase_date", purchased), ("amount", amount), ("reason", reason), ("prior_disputes_12m", previous), ("contacted_merchant", contacted)):
        if value is None:
            missing.append(field)
    criteria = {}
    if opened is not None and today is not None:
        criteria["account_age_at_least_60_days"] = (today - opened).days >= 60
    if reason is not None:
        criteria["eligible_reason"] = reason in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}
        if reason == "goods_services_not_received" and purchased is not None and today is not None:
            criteria["not_received_purchase_more_than_30_days_ago"] = (today - purchased).days > 30
        elif reason != "goods_services_not_received":
            criteria["not_received_purchase_more_than_30_days_ago"] = True
    if amount is not None and tier in PROVISIONAL_CAPS:
        criteria["amount_within_range"] = Decimal("25") <= amount <= PROVISIONAL_CAPS[tier]
    if previous is not None:
        try:
            criteria["no_more_than_two_prior_disputes"] = int(previous) <= 2
        except (TypeError, ValueError):
            raise ValueError("prior_disputes_12m must be an integer")
    if reason is not None and contacted is not None:
        criteria["merchant_contact_requirement"] = bool(contacted) if reason != "unauthorized_fraudulent_charge" else True
    eligible = None if missing else all(criteria.values())
    return {"kind": "provisional_credit", "eligible": eligible, "missing": missing, "criteria": criteria, "maximum_amount": str(PROVISIONAL_CAPS[tier]) if tier in PROVISIONAL_CAPS else None}


def cli(data):
    missing = []
    tier = data.get("tier")
    if tier not in CLI_RULES:
        missing.append("tier (entry, mid, or premium)")
    current_limit = decimal(data.get("current_credit_limit"), "current_credit_limit")
    increase = decimal(data.get("requested_increase_amount"), "requested_increase_amount")
    opened = parse_date(data.get("account_open_date")) if data.get("account_open_date") else None
    today = parse_date(data.get("current_date")) if data.get("current_date") else None
    utilization = decimal(data.get("utilization_percent"), "utilization_percent")
    approved_date = parse_date(data.get("last_approved_request_date")) if data.get("last_approved_request_date") else None
    payments = data.get("consecutive_on_time_months")
    disputes = data.get("has_pending_disputes")
    replacement = data.get("has_pending_replacement")
    past_due = decimal(data.get("past_due_amount"), "past_due_amount")
    for field, value in (("current_credit_limit", current_limit), ("requested_increase_amount", increase), ("account_open_date", opened), ("current_date", today), ("utilization_percent", utilization), ("consecutive_on_time_months", payments), ("has_pending_disputes", disputes), ("has_pending_replacement", replacement), ("past_due_amount", past_due)):
        if value is None:
            missing.append(field)
    criteria = {}
    max_increase = None
    cooldown_eligible_on = None
    if tier in CLI_RULES and current_limit is not None:
        max_increase = current_limit * CLI_RULES[tier]["max_fraction"]
        if increase is not None:
            criteria["requested_amount_within_limit"] = Decimal("0") < increase <= max_increase
    if tier in CLI_RULES and opened is not None and today is not None:
        criteria["account_age_requirement"] = (today - opened).days >= CLI_RULES[tier]["age_days"]
    if tier in CLI_RULES:
        if approved_date is None:
            criteria["cooldown_elapsed"] = True
        elif today is not None:
            cooldown_eligible_on = approved_date + timedelta(days=CLI_RULES[tier]["cooldown_days"])
            criteria["cooldown_elapsed"] = today >= cooldown_eligible_on
    if tier in CLI_RULES and utilization is not None:
        criteria["utilization_strictly_below_threshold"] = utilization < CLI_RULES[tier]["utilization_lt"]
    if tier in CLI_RULES and payments is not None:
        try:
            criteria["payment_history_requirement"] = int(payments) >= CLI_RULES[tier]["on_time_months"]
        except (TypeError, ValueError):
            raise ValueError("consecutive_on_time_months must be an integer")
    if disputes is not None:
        criteria["no_pending_disputes"] = not bool(disputes)
    if replacement is not None:
        criteria["no_pending_replacement"] = not bool(replacement)
    if past_due is not None:
        criteria["no_past_due_balance"] = past_due <= Decimal("0")
    eligible = None if missing else all(criteria.values())
    return {"kind": "cli", "eligible": eligible, "missing": missing, "criteria": criteria, "maximum_increase_amount": str(max_increase) if max_increase is not None else None, "new_credit_limit_if_approved": str(current_limit + increase) if current_limit is not None and increase is not None else None, "cooldown_eligible_on": cooldown_eligible_on.isoformat() if cooldown_eligible_on else None}


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        kind = data.get("kind")
        if kind == "provisional_credit":
            emit(provisional(data))
        elif kind == "cli":
            emit(cli(data))
        else:
            raise ValueError("kind must be provisional_credit or cli")
    except Exception as exc:
        emit({"error": str(exc)})
        sys.exit(2)


if __name__ == "__main__":
    main()
