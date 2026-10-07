#!/usr/bin/env python3
"""Assess provisional-credit eligibility from normalized, verified dispute facts.

Reads one JSON object on stdin and emits one JSON object on stdout. Required keys:
as_of_date, account_open_date, card_tier, purchase_date, transaction_amount,
dispute_reason, contacted_merchant, disputes_past_12_months.
"""
from __future__ import annotations

import json
import sys
from policy import PROVISIONAL_MAXIMUMS, decimal, json_decimal, parse_date, tier

QUALIFYING = {
    "unauthorized_fraudulent_charge",
    "duplicate_charge",
    "goods_services_not_received",
}
VALID_REASONS = QUALIFYING | {
    "incorrect_amount", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}

def main() -> None:
    try:
        data = json.load(sys.stdin)
        required = ["as_of_date", "account_open_date", "card_tier", "purchase_date", "transaction_amount", "dispute_reason", "contacted_merchant", "disputes_past_12_months"]
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError("missing required fields: " + ", ".join(missing))
        as_of = parse_date(data["as_of_date"])
        opened = parse_date(data["account_open_date"])
        purchased = parse_date(data["purchase_date"])
        if opened > as_of or purchased > as_of:
            raise ValueError("account_open_date and purchase_date cannot be in the future")
        card_tier = tier(data["card_tier"])
        amount = decimal(data["transaction_amount"], "transaction_amount")
        count = int(data["disputes_past_12_months"])
        if count < 0:
            raise ValueError("disputes_past_12_months cannot be negative")
        reason = data["dispute_reason"]
        if reason not in VALID_REASONS:
            raise ValueError("unsupported dispute_reason")
        if not isinstance(data["contacted_merchant"], bool):
            raise ValueError("contacted_merchant must be boolean")

        age_days = (as_of - opened).days
        purchase_age_days = (as_of - purchased).days
        cap = PROVISIONAL_MAXIMUMS[card_tier]
        reason_qualifies = reason in QUALIFYING
        delivery_age_ok = reason != "goods_services_not_received" or purchase_age_days > 30
        contacted_ok = reason == "unauthorized_fraudulent_charge" or data["contacted_merchant"]
        criteria = {
            "account_open_at_least_60_days": age_days >= 60,
            "qualifying_reason": reason_qualifies,
            "goods_not_received_purchase_over_30_days": delivery_age_ok,
            "amount_at_least_25": amount >= Decimal("25.00"),
            "amount_within_tier_cap": amount <= cap,
            "no_more_than_two_prior_disputes_in_12_months": count <= 2,
            "merchant_contact_requirement": contacted_ok,
        }
        reasons = [name for name, passed in criteria.items() if not passed]
        output = {
            "eligible": not reasons,
            "criteria": criteria,
            "failed_criteria": reasons,
            "derived": {
                "account_age_days": age_days,
                "purchase_age_days": purchase_age_days,
                "transaction_amount": json_decimal(amount),
                "tier_maximum": json_decimal(cap),
                "disputes_past_12_months": count,
            },
        }
    except Exception as exc:
        output = {"error": str(exc), "eligible": False}
    print(json.dumps(output, sort_keys=True))

if __name__ == "__main__":
    main()
