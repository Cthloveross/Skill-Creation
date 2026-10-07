#!/usr/bin/env python3
"""Evaluate normalized credit-card dispute, replacement, and CLI facts.

Input and output are JSON objects on stdin/stdout. This program performs no tool calls.
Dates accepted: YYYY-MM-DD, MM/DD/YYYY, or timestamps beginning with either form.
"""
import json
import sys
from datetime import datetime, date

CLI_TIERS = {
    "Bronze Rewards Card": "entry", "EcoCard": "entry", "Business Bronze Rewards Card": "entry",
    "Silver Rewards Card": "mid", "Business Silver Rewards Card": "mid", "Green Rewards Card": "mid", "Silver Zoom Card": "mid",
    "Gold Rewards Card": "premium", "Business Gold Rewards Card": "premium",
}
PROVISIONAL_LIMITS = {
    "Bronze Rewards Card": 2500.0, "EcoCard": 2500.0, "Business Bronze Rewards Card": 2500.0, "Crypto-Cash Back Card": 2500.0,
    "Silver Rewards Card": 5000.0, "Business Silver Rewards Card": 5000.0, "Green Rewards Card": 5000.0, "Silver Zoom Card": 5000.0,
    "Gold Rewards Card": 10000.0, "Business Gold Rewards Card": 10000.0,
    "Platinum Rewards Card": 15000.0, "Business Platinum Rewards Card": 15000.0,
    "Diamond Elite Card": 25000.0,
}
TIER_RULES = {
    "entry": {"age": 120, "cooldown": 120, "utilization": 70.0, "payment_months": 6, "increase_fraction": 0.25},
    "mid": {"age": 90, "cooldown": 90, "utilization": 80.0, "payment_months": 3, "increase_fraction": 0.50},
    "premium": {"age": 60, "cooldown": 60, "utilization": 90.0, "payment_months": 3, "increase_fraction": 0.50},
}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    candidates = [value, value[:10]]
    for candidate in candidates:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    return None


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def days_between(later, earlier):
    return (later - earlier).days if later and earlier else None


def tri(passes, missing, failures):
    if missing:
        return None
    return not failures


def provisional(now, account, dispute, card_type):
    missing, failures = [], []
    opened = parse_date(account.get("opened_date"))
    amount = number(dispute.get("amount"))
    purchase = parse_date(dispute.get("purchase_date"))
    reason = dispute.get("reason")
    contacted = dispute.get("contacted_merchant")
    prior = dispute.get("prior_dispute_dates")
    age = days_between(now, opened)
    limit = PROVISIONAL_LIMITS.get(card_type)
    if age is None: missing.append("account.opened_date")
    elif age < 60: failures.append("account_under_60_days")
    if amount is None: missing.append("dispute.amount")
    elif amount < 25: failures.append("amount_under_25")
    if limit is None: missing.append("provisional_tier_limit")
    elif amount is not None and amount > limit: failures.append("amount_exceeds_tier_limit")
    qualifying = {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}
    if reason not in qualifying: failures.append("nonqualifying_dispute_reason")
    if reason == "goods_services_not_received":
        age_of_purchase = days_between(now, purchase)
        if age_of_purchase is None: missing.append("dispute.purchase_date")
        elif age_of_purchase <= 30: failures.append("goods_not_received_within_30_days")
    if reason and reason != "unauthorized_fraudulent_charge":
        if not isinstance(contacted, bool): missing.append("dispute.contacted_merchant")
        elif not contacted: failures.append("merchant_not_contacted")
    if not isinstance(prior, list):
        missing.append("dispute.prior_dispute_dates")
    else:
        parsed = [parse_date(x) for x in prior]
        if any(x is None for x in parsed): missing.append("valid prior dispute dates")
        else:
            count = sum(0 <= days_between(now, d) <= 365 for d in parsed)
            if count > 2: failures.append("more_than_two_prior_disputes_in_12_months")
    return {"eligible": tri(True, missing, failures), "missing": missing, "failures": failures, "tier_limit": limit}


def replacement(replacement):
    missing, failures = [], []
    orders = replacement.get("pending_orders")
    count = replacement.get("replacements_last_60_days")
    if not isinstance(orders, list):
        missing.append("replacement.pending_orders")
    else:
        nonfinal = []
        for order in orders:
            status = order.get("status") if isinstance(order, dict) else None
            if not isinstance(status, str):
                missing.append("replacement order status")
            elif status.lower() not in FINAL_REPLACEMENT_STATUSES:
                nonfinal.append(status)
        if nonfinal: failures.append("pending_replacement_order")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        missing.append("replacement.replacements_last_60_days")
    elif count >= 4:
        failures.append("premium_replacement_limit_reached")
    return {"eligible": tri(True, missing, failures), "missing": missing, "failures": failures}


def cli(now, account, cli, tier, replacement_assessment):
    out = {"tier": tier, "pre_submission": {}, "post_submission": {}}
    if tier not in TIER_RULES:
        out["pre_submission"] = {"can_submit": None, "missing": ["supported CLI tier"], "failures": ["unsupported_card_tier"]}
        out["post_submission"] = {"decision": None, "missing": ["supported CLI tier"], "failures": ["unsupported_card_tier"]}
        return out
    rules = TIER_RULES[tier]
    limit = number(account.get("credit_limit"))
    request = cli.get("requested_increase_amount")
    request_num = number(request)
    pre_missing, pre_failures = [], []
    if limit is None or limit <= 0: pre_missing.append("account.credit_limit")
    if not isinstance(request, int) or isinstance(request, bool): pre_missing.append("cli.requested_increase_amount integer")
    elif request <= 0: pre_failures.append("nonpositive_requested_increase")
    max_increase = limit * rules["increase_fraction"] if limit else None
    if not pre_missing and request_num > max_increase: pre_failures.append("requested_amount_exceeds_limit")
    out["pre_submission"] = {"can_submit": tri(True, pre_missing, pre_failures), "missing": pre_missing, "failures": pre_failures, "maximum_increase": max_increase}
    missing, failures = [], []
    opened = parse_date(account.get("opened_date"))
    age = days_between(now, opened)
    if age is None: missing.append("account.opened_date")
    elif age < rules["age"]: failures.append("insufficient_account_age")
    approved_dates = cli.get("approved_request_dates")
    if not isinstance(approved_dates, list): missing.append("cli.approved_request_dates")
    else:
        parsed = [parse_date(x) for x in approved_dates]
        if any(x is None for x in parsed): missing.append("valid approved CLI request dates")
        else:
            earlier = [d for d in parsed if d <= now]
            if earlier and days_between(now, max(earlier)) < rules["cooldown"]: failures.append("cooldown_period_active")
    pending_disputes = cli.get("has_pending_disputes")
    if not isinstance(pending_disputes, bool): missing.append("cli.has_pending_disputes")
    elif pending_disputes: failures.append("pending_disputes")
    if replacement_assessment["eligible"] is None: missing.extend(replacement_assessment["missing"])
    elif "pending_replacement_order" in replacement_assessment["failures"]: failures.append("pending_replacement_card")
    past_due = number(account.get("past_due_amount"))
    if past_due is None: missing.append("account.past_due_amount")
    elif past_due > 0: failures.append("past_due_balance")
    balance = number(account.get("current_balance"))
    if balance is None or limit is None or limit <= 0: missing.append("account balance and positive credit limit")
    elif balance / limit * 100 >= rules["utilization"]: failures.append("high_utilization")
    months = cli.get("consecutive_on_time_months")
    if not isinstance(months, int) or isinstance(months, bool) or months < 0: missing.append("cli.consecutive_on_time_months")
    elif months < rules["payment_months"]: failures.append("insufficient_payment_history")
    decision = None if missing else ("approve" if not failures else "deny")
    out["post_submission"] = {"decision": decision, "missing": sorted(set(missing)), "failures": failures, "new_credit_limit": (limit + request_num if decision == "approve" else None)}
    return out


def main(data):
    now = parse_date(data.get("now"))
    account = data.get("account") if isinstance(data.get("account"), dict) else {}
    dispute = data.get("dispute") if isinstance(data.get("dispute"), dict) else {}
    replacement_data = data.get("replacement") if isinstance(data.get("replacement"), dict) else {}
    cli_data = data.get("cli") if isinstance(data.get("cli"), dict) else {}
    if now is None:
        return {"error": "now is required and must begin with YYYY-MM-DD or be MM/DD/YYYY"}
    card_type = account.get("card_type")
    tier = CLI_TIERS.get(card_type)
    repl = replacement(replacement_data)
    return {
        "card_type": card_type,
        "cli_tier": tier,
        "provisional_credit": provisional(now, account, dispute, card_type),
        "replacement": repl,
        "cli": cli(now, account, cli_data, tier, repl),
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON value must be an object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
