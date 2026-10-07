#!/usr/bin/env python3
"""Deterministically evaluate the documented provisional-credit criteria.

Reads one JSON object from stdin and emits either a decision object or an error
object on stdout. This helper makes no bank calls and is not an authorization to
file a dispute.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

DATE_FORMAT = "%m/%d/%Y"
LIMITS = {
    "entry": Decimal("2500.00"),
    "mid": Decimal("5000.00"),
    "premium": Decimal("10000.00"),
    "elite": Decimal("15000.00"),
    "invitation": Decimal("25000.00"),
}
QUALIFYING = {
    "unauthorized_fraudulent_charge",
    "duplicate_charge",
    "goods_services_not_received",
}
ALL_REASONS = QUALIFYING | {
    "incorrect_amount",
    "goods_services_not_as_described",
    "canceled_subscription_still_charging",
    "refund_never_processed",
}


def parse_date(value, name):
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an MM/DD/YYYY string")
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError as exc:
        raise ValueError(f"{name} must be a valid MM/DD/YYYY date") from exc


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        opened = parse_date(data.get("account_open_date"), "account_open_date")
        as_of = parse_date(data.get("as_of_date"), "as_of_date")
        purchased = parse_date(data.get("purchase_date"), "purchase_date")
        if opened > as_of or purchased > as_of:
            raise ValueError("account_open_date and purchase_date cannot be after as_of_date")
        try:
            amount = Decimal(str(data.get("amount")))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("amount must be numeric") from exc
        tier = str(data.get("card_tier", "")).strip().lower()
        if tier not in LIMITS:
            raise ValueError("card_tier must be entry, mid, premium, elite, or invitation")
        prior = data.get("prior_disputes_12_months")
        if isinstance(prior, bool) or not isinstance(prior, int) or prior < 0:
            raise ValueError("prior_disputes_12_months must be a non-negative integer")
        contacted = data.get("contacted_merchant")
        if not isinstance(contacted, bool):
            raise ValueError("contacted_merchant must be boolean")
        reason = data.get("dispute_reason")
        if reason not in ALL_REASONS:
            raise ValueError("dispute_reason is not an allowed dispute reason")

        failed = []
        if (as_of - opened).days < 60:
            failed.append("account_open_less_than_60_days")
        if reason not in QUALIFYING:
            failed.append("reason_not_provisional_credit_eligible")
        if reason == "goods_services_not_received" and (as_of - purchased).days <= 30:
            failed.append("goods_not_received_purchase_not_more_than_30_days_old")
        if amount < Decimal("25.00"):
            failed.append("amount_under_25")
        elif amount > LIMITS[tier]:
            failed.append("amount_exceeds_tier_limit")
        if prior > 2:
            failed.append("more_than_two_prior_disputes_in_12_months")
        if reason != "unauthorized_fraudulent_charge" and not contacted:
            failed.append("merchant_not_contacted_for_non_fraud_dispute")
        result = {
            "eligible": not failed,
            "failed_conditions": failed,
            "tier_limit": float(LIMITS[tier]),
        }
    except Exception as exc:
        result = {"eligible": False, "error": str(exc), "failed_conditions": ["invalid_or_incomplete_input"]}
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
