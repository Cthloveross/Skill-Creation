#!/usr/bin/env python3
"""Evaluate documented provisional-credit conditions from JSON stdin.

This script is pure computation. Input fields are documented in SKILL.md. Output:
{"eligible": bool, "failed_criteria": [str], "account_age_days": int|None,
 "purchase_age_days": int|None, "tier_cap": number|None}
"""
import json
import sys
from datetime import date, datetime

CAPS = {
    "entry": 2500.0,
    "mid": 5000.0,
    "premium": 10000.0,
    "elite": 15000.0,
    "invitation": 25000.0,
}
ELIGIBLE_REASONS = {
    "unauthorized_fraudulent_charge",
    "duplicate_charge",
    "goods_services_not_received",
}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("date must be YYYY-MM-DD or MM/DD/YYYY")


def main(data):
    errors = []
    failed = []
    try:
        today = parse_date(data.get("current_date"))
        opened = parse_date(data.get("account_open_date"))
        purchased = parse_date(data.get("purchase_date"))
    except ValueError as exc:
        return {"eligible": False, "failed_criteria": ["invalid_date"], "error": str(exc)}

    account_age = (today - opened).days
    purchase_age = (today - purchased).days
    tier = data.get("card_tier")
    cap = CAPS.get(tier)
    try:
        amount = float(data.get("amount"))
    except (TypeError, ValueError):
        amount = None
        errors.append("invalid_amount")
    reason = data.get("reason")
    contacted = data.get("contacted_merchant")
    prior = data.get("prior_disputes_last_12_months")

    if account_age < 60:
        failed.append("account_less_than_60_days")
    if reason not in ELIGIBLE_REASONS:
        failed.append("reason_not_eligible")
    if reason == "goods_services_not_received" and purchase_age <= 30:
        failed.append("goods_not_received_purchase_not_over_30_days")
    if cap is None:
        failed.append("unknown_card_tier")
    if amount is None:
        failed.append("invalid_amount")
    elif amount < 25.0:
        failed.append("amount_under_25")
    elif cap is not None and amount > cap:
        failed.append("amount_exceeds_tier_cap")
    if not isinstance(prior, int) or isinstance(prior, bool):
        failed.append("invalid_prior_dispute_count")
    elif prior > 2:
        failed.append("more_than_two_prior_disputes")
    elif prior < 0:
        failed.append("invalid_prior_dispute_count")
    if reason != "unauthorized_fraudulent_charge" and contacted is not True:
        failed.append("merchant_not_contacted_for_nonfraud")
    if account_age < 0:
        failed.append("invalid_account_open_date")
    if purchase_age < 0:
        failed.append("invalid_purchase_date")

    # Preserve stable order while avoiding duplicated failures.
    unique_failed = list(dict.fromkeys(errors + failed))
    return {
        "eligible": not unique_failed,
        "failed_criteria": unique_failed,
        "account_age_days": account_age,
        "purchase_age_days": purchase_age,
        "tier_cap": cap,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"eligible": False, "failed_criteria": ["invalid_input"], "error": str(exc)}))
        sys.exit(1)
