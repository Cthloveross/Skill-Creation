#!/usr/bin/env python3
"""Validate one dispute intake record and calculate provisional-credit eligibility.

Input JSON:
  as_of_date, account_open_date, card_tier, prior_disputes_12_months,
  transaction_amount, purchase_date, and dispute (the filing-tool payload).
Dates are MM/DD/YYYY. card_tier is entry, mid, premium, elite, or invitation.
Output JSON reports submission-field errors and policy reasons. This utility never
calls bank tools or files a dispute.
"""
import json
import sys
from datetime import datetime

DATE_FMT = "%m/%d/%Y"
REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
ACTIONS = {"keep_active", "cancel_and_reissue"}
LIMITS = {"entry": 2500.0, "mid": 5000.0, "premium": 10000.0,
          "elite": 15000.0, "invitation": 25000.0}


def parse_date(value, field, invalid):
    if not isinstance(value, str):
        invalid.append(field + " must be MM/DD/YYYY")
        return None
    try:
        return datetime.strptime(value, DATE_FMT).date()
    except ValueError:
        invalid.append(field + " must be MM/DD/YYYY")
        return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"error": "input must be one JSON object: " + str(exc)}))
        return

    dispute = data.get("dispute")
    if not isinstance(dispute, dict):
        print(json.dumps({"error": "dispute must be an object"}))
        return

    missing, invalid, policy = [], [], []
    required = ["transaction_id", "card_action", "card_last_4_digits", "full_name",
                "user_id", "phone", "email", "address", "contacted_merchant",
                "purchase_date", "issue_noticed_date", "dispute_reason",
                "resolution_requested"]
    for field in required:
        if field not in dispute or dispute[field] in (None, ""):
            missing.append(field)

    if dispute.get("card_action") not in ACTIONS:
        invalid.append("card_action is not an allowed value")
    last4 = dispute.get("card_last_4_digits")
    if not isinstance(last4, str) or len(last4) != 4 or not last4.isdigit():
        invalid.append("card_last_4_digits must be exactly four digits")
    if "contacted_merchant" in dispute and not isinstance(dispute["contacted_merchant"], bool):
        invalid.append("contacted_merchant must be boolean")
    if dispute.get("dispute_reason") not in REASONS:
        invalid.append("dispute_reason is not an allowed value")
    resolution = dispute.get("resolution_requested")
    if resolution not in RESOLUTIONS:
        invalid.append("resolution_requested is not an allowed value")
    if resolution == "partial_refund":
        amount = dispute.get("partial_refund_amount")
        if amount is None:
            missing.append("partial_refund_amount")
        elif not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount <= 0:
            invalid.append("partial_refund_amount must be a positive number")
    elif "partial_refund_amount" in dispute and dispute["partial_refund_amount"] is not None:
        invalid.append("partial_refund_amount is permitted only for partial_refund")

    purchase = parse_date(data.get("purchase_date", dispute.get("purchase_date")), "purchase_date", invalid)
    payload_purchase = parse_date(dispute.get("purchase_date"), "dispute.purchase_date", invalid)
    noticed = parse_date(dispute.get("issue_noticed_date"), "issue_noticed_date", invalid)
    as_of = parse_date(data.get("as_of_date"), "as_of_date", invalid)
    opened = parse_date(data.get("account_open_date"), "account_open_date", invalid)
    if purchase and payload_purchase and purchase != payload_purchase:
        invalid.append("purchase_date does not match the verified transaction date")
    if noticed and purchase and noticed < purchase:
        invalid.append("issue_noticed_date cannot precede purchase_date")

    eligible = True
    reason = dispute.get("dispute_reason")
    tier = data.get("card_tier")
    try:
        amount = float(data.get("transaction_amount"))
    except (TypeError, ValueError):
        amount = None
        invalid.append("transaction_amount must be numeric")
    try:
        prior = int(data.get("prior_disputes_12_months"))
        if prior < 0:
            raise ValueError
    except (TypeError, ValueError):
        prior = None
        invalid.append("prior_disputes_12_months must be a nonnegative integer")

    if tier not in LIMITS:
        invalid.append("card_tier must be entry, mid, premium, elite, or invitation")
    if opened and as_of and (as_of - opened).days < 60:
        policy.append("account has been open fewer than 60 days")
    if reason not in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}:
        policy.append("dispute reason is not eligible for provisional credit")
    if reason == "goods_services_not_received" and purchase and as_of and (as_of - purchase).days <= 30:
        policy.append("goods/services-not-received purchase is not more than 30 days old")
    if amount is not None and (amount < 25 or (tier in LIMITS and amount > LIMITS[tier])):
        policy.append("transaction amount is outside the tier provisional-credit limit")
    if prior is not None and prior > 2:
        policy.append("customer has filed more than two disputes in the prior 12 months")
    if reason and reason != "unauthorized_fraudulent_charge" and dispute.get("contacted_merchant") is not True:
        policy.append("non-fraud dispute lacks confirmed merchant contact")
    if invalid:
        eligible = False
    elif policy:
        eligible = False

    output = {
        "valid_for_submission": not missing and not invalid,
        "eligible_for_provisional_credit": eligible,
        "missing": missing,
        "invalid": invalid,
        "reasons": policy,
    }
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
