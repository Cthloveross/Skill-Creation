#!/usr/bin/env python3
"""Deterministic, side-effect-free CLI and provisional-credit assessment.

Read one JSON object from stdin and emit an assessment JSON object. Monetary values
are numeric dollars. Dates use YYYY-MM-DD. This script does not call banking tools.
"""
import json
import sys
from datetime import date, datetime

TIER = {
    "entry": {"age": 120, "cooldown": 120, "util": 0.70, "increase": 0.25, "payments": 6, "provisional_max": 2500.0},
    "mid": {"age": 90, "cooldown": 90, "util": 0.80, "increase": 0.50, "payments": 3, "provisional_max": 5000.0},
    "premium": {"age": 60, "cooldown": 60, "util": 0.90, "increase": 0.50, "payments": 3, "provisional_max": 10000.0},
    "elite": {"provisional_max": 15000.0},
    "invitation": {"provisional_max": 25000.0},
}

def parse_day(value, field, missing):
    if not isinstance(value, str):
        missing.append(field)
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        missing.append(field + " (YYYY-MM-DD)")
        return None

def number(data, key, missing):
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        missing.append(key)
        return None
    return float(value)

def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        print(json.dumps({"error": "input must be one JSON object", "detail": str(exc)}))
        return 2
    if not isinstance(data, dict):
        print(json.dumps({"error": "input must be one JSON object"}))
        return 2

    missing = []
    tier_name = data.get("tier")
    rules = TIER.get(tier_name)
    if rules is None:
        missing.append("tier (entry|mid|premium|elite|invitation)")
        rules = {}
    now = parse_day(data.get("now"), "now", missing)
    opened = parse_day(data.get("account_open_date"), "account_open_date", missing)
    balance = number(data, "current_balance", missing)
    limit = number(data, "current_limit", missing)
    requested_total = number(data, "requested_new_limit", missing)
    past_due = number(data, "past_due_amount", missing)

    cli_failed = []
    calculations = {}
    if now and opened:
        calculations["account_age_days"] = (now - opened).days
    if limit is not None and limit > 0 and balance is not None:
        calculations["utilization_percent"] = balance / limit * 100
    elif limit is not None and limit <= 0:
        cli_failed.append("invalid_current_limit")

    if {"age", "cooldown", "util", "increase", "payments"}.issubset(rules):
        if now and opened and (now - opened).days < rules["age"]:
            cli_failed.append("insufficient_account_age")
        if requested_total is not None and limit is not None:
            increase = requested_total - limit
            calculations["requested_increase"] = increase
            calculations["max_increase"] = limit * rules["increase"]
            if increase <= 0 or increase > limit * rules["increase"]:
                cli_failed.append("requested_amount_exceeds_limit")
        dates = data.get("prior_approved_request_dates")
        if not isinstance(dates, list):
            missing.append("prior_approved_request_dates")
        elif now:
            parsed = [parse_day(v, "prior_approved_request_dates item", missing) for v in dates]
            parsed = [v for v in parsed if v is not None and v <= now]
            if parsed and (now - max(parsed)).days < rules["cooldown"]:
                cli_failed.append("cooldown_period_active")
        if balance is not None and limit is not None and limit > 0 and balance / limit >= rules["util"]:
            cli_failed.append("high_utilization")
        payments = data.get("payment_months_on_time")
        if not isinstance(payments, list):
            missing.append("payment_months_on_time")
        elif len(payments) < rules["payments"] or not all(x is True for x in payments[:rules["payments"]]):
            cli_failed.append("insufficient_payment_history")
    else:
        cli_failed.append("unsupported_cli_tier")

    if data.get("has_active_dispute") is not False:
        if "has_active_dispute" not in data:
            missing.append("has_active_dispute")
        else:
            cli_failed.append("pending_disputes")
    if data.get("has_pending_replacement") is not False:
        if "has_pending_replacement" not in data:
            missing.append("has_pending_replacement")
        else:
            cli_failed.append("pending_replacement_card")
    if data.get("account_current") is not True or (past_due is not None and past_due > 0):
        if "account_current" not in data:
            missing.append("account_current")
        else:
            cli_failed.append("past_due_balance")

    provisional_failed = []
    txn_day = parse_day(data.get("transaction_date"), "transaction_date", missing)
    amount = number(data, "transaction_amount", missing)
    reason = data.get("dispute_reason")
    merchant_contact = data.get("contacted_merchant")
    disputes = data.get("prior_disputes_last_12_months")
    if not isinstance(disputes, int) or isinstance(disputes, bool) or disputes < 0:
        missing.append("prior_disputes_last_12_months")
    if now and opened and (now - opened).days < 60:
        provisional_failed.append("account_under_60_days")
    if reason not in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}:
        provisional_failed.append("unsupported_dispute_reason")
    if reason == "goods_services_not_received" and now and txn_day and (now - txn_day).days <= 30:
        provisional_failed.append("goods_not_received_purchase_not_over_30_days")
    maximum = rules.get("provisional_max")
    if amount is not None:
        calculations["provisional_credit_maximum"] = maximum
        if amount < 25 or maximum is None or amount > maximum:
            provisional_failed.append("amount_outside_tier_limit")
    if isinstance(disputes, int) and not isinstance(disputes, bool) and disputes > 2:
        provisional_failed.append("too_many_prior_disputes")
    if reason != "unauthorized_fraudulent_charge" and merchant_contact is not True:
        provisional_failed.append("merchant_not_contacted")

    output = {
        "missing": sorted(set(missing)),
        "calculations": calculations,
        "cli": {"eligible": not missing and not cli_failed, "failed": sorted(set(cli_failed))},
        "provisional_credit": {
            "eligible": not missing and not provisional_failed,
            "failed": sorted(set(provisional_failed)),
        },
    }
    print(json.dumps(output, sort_keys=True))
    return 0

if __name__ == "__main__":
    sys.exit(main())
