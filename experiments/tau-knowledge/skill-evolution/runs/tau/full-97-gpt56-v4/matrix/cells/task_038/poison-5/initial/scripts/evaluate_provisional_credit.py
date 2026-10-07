#!/usr/bin/env python3
"""Evaluate documented provisional-credit eligibility from JSON stdin."""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

DATE_FMT = "%m/%d/%Y"
TIER_CAPS = {
    "Bronze Rewards Card": Decimal("2500"),
    "EcoCard": Decimal("2500"),
    "Business Bronze Rewards Card": Decimal("2500"),
    "Crypto-Cash Back Card": Decimal("2500"),
    "Silver Rewards Card": Decimal("5000"),
    "Business Silver Rewards Card": Decimal("5000"),
    "Green Rewards Card": Decimal("5000"),
    "Silver Zoom Card": Decimal("5000"),
    "Gold Rewards Card": Decimal("10000"),
    "Business Gold Rewards Card": Decimal("10000"),
    "Platinum Rewards Card": Decimal("15000"),
    "Business Platinum Rewards Card": Decimal("15000"),
    "Diamond Elite Card": Decimal("25000"),
}
QUALIFYING = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"
}


def parse_date(value, field, missing):
    if not isinstance(value, str) or not value:
        missing.append(field)
        return None
    try:
        return datetime.strptime(value, DATE_FMT).date()
    except ValueError:
        missing.append(field + " (must be MM/DD/YYYY)")
        return None


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": "invalid JSON: " + str(exc)}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"ok": False, "error": "input must be an object"}))
        return

    missing = []
    opened = parse_date(data.get("account_open_date"), "account_open_date", missing)
    as_of = parse_date(data.get("as_of_date"), "as_of_date", missing)
    purchase = parse_date(data.get("purchase_date"), "purchase_date", missing)
    card_type = data.get("card_type")
    reason = data.get("reason")
    contacted = data.get("contacted_merchant")
    history = data.get("prior_disputes_last_12_months")
    amount = None
    try:
        amount = Decimal(str(data.get("amount"))).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        missing.append("amount (must be numeric)")
    if card_type not in TIER_CAPS:
        missing.append("card_type (unsupported or missing)")
    if reason not in {
        "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
        "goods_services_not_received", "goods_services_not_as_described",
        "canceled_subscription_still_charging", "refund_never_processed"
    }:
        missing.append("reason (invalid or missing)")
    if not isinstance(contacted, bool):
        missing.append("contacted_merchant (must be boolean)")
    if not isinstance(history, int) or isinstance(history, bool) or history < 0:
        missing.append("prior_disputes_last_12_months (must be a nonnegative integer)")

    if missing:
        print(json.dumps({"ok": True, "decision": "undetermined", "eligible_for_provisional_credit": None,
                          "checks": {}, "missing": missing}))
        return

    checks = {
        "account_open_at_least_60_days": (as_of - opened).days >= 60,
        "qualifying_reason": reason in QUALIFYING,
        "amount_at_least_25": amount >= Decimal("25.00"),
        "amount_within_tier_cap": amount <= TIER_CAPS[card_type],
        "no_more_than_two_prior_disputes": history <= 2,
        "merchant_contact_requirement": reason == "unauthorized_fraudulent_charge" or contacted,
        "not_received_purchase_more_than_30_days": (
            reason != "goods_services_not_received" or (as_of - purchase).days > 30
        ),
    }
    eligible = all(checks.values())
    print(json.dumps({"ok": True, "decision": "eligible" if eligible else "ineligible",
                      "eligible_for_provisional_credit": eligible, "checks": checks, "missing": []}))


if __name__ == "__main__":
    main()
