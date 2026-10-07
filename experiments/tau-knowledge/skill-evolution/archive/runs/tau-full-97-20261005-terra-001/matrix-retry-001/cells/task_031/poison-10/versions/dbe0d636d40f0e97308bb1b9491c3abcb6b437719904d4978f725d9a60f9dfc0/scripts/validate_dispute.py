#!/usr/bin/env python3
"""Validate and prepare a credit-card dispute filing request.

Input: one JSON object on stdin. Required key ``dispute`` is an object containing
all filing fields except that eligible_for_provisional_credit may be omitted and
will be calculated. Supplemental keys used for eligibility are transaction_amount,
card_type, account_open_date, as_of_date, and prior_dispute_count_12_months.
Output: one JSON object with errors, an eligibility assessment, and tool_arguments
only when the filing request is complete and eligibility is determinate.
"""
import json
import math
import sys
from datetime import datetime

REASONS = {
    "unauthorized_fraudulent_charge",
    "duplicate_charge",
    "incorrect_amount",
    "goods_services_not_received",
    "goods_services_not_as_described",
    "canceled_subscription_still_charging",
    "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
ACTIONS = {"keep_active", "cancel_and_reissue"}
TIER_LIMITS = {
    "Bronze Rewards Card": 2500.0,
    "EcoCard": 2500.0,
    "Business Bronze Rewards Card": 2500.0,
    "Crypto-Cash Back Card": 2500.0,
    "Silver Rewards Card": 5000.0,
    "Business Silver Rewards Card": 5000.0,
    "Green Rewards Card": 5000.0,
    "Silver Zoom Card": 5000.0,
    "Gold Rewards Card": 10000.0,
    "Business Gold Rewards Card": 10000.0,
    "Platinum Rewards Card": 15000.0,
    "Business Platinum Rewards Card": 15000.0,
    "Diamond Elite Card": 25000.0,
}
CATEGORICALLY_INELIGIBLE = {
    "incorrect_amount",
    "goods_services_not_as_described",
    "canceled_subscription_still_charging",
    "refund_never_processed",
}


def parse_date(value, label, errors):
    if not isinstance(value, str):
        errors.append(f"{label} must be a MM/DD/YYYY string")
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        errors.append(f"{label} must use a real MM/DD/YYYY date")
        return None


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def eligibility(data, dispute, purchase_date):
    """Return eligibility using known facts, retaining missing facts if needed."""
    reason = dispute.get("dispute_reason")
    failed, missing = [], []
    if reason in CATEGORICALLY_INELIGIBLE:
        failed.append("dispute reason is not eligible for provisional credit")
        return False, failed, missing
    if reason not in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}:
        missing.append("a valid dispute_reason")
        return None, failed, missing

    as_of = None
    if "as_of_date" not in data:
        missing.append("as_of_date for eligibility")
    else:
        try:
            as_of = datetime.strptime(data["as_of_date"], "%m/%d/%Y").date()
        except (TypeError, ValueError):
            missing.append("a valid as_of_date (MM/DD/YYYY)")

    open_date = None
    if "account_open_date" not in data:
        missing.append("account_open_date")
    else:
        try:
            open_date = datetime.strptime(data["account_open_date"], "%m/%d/%Y").date()
        except (TypeError, ValueError):
            missing.append("a valid account_open_date (MM/DD/YYYY)")
    if as_of and open_date:
        if as_of < open_date:
            failed.append("account open date is after the eligibility date")
        elif (as_of - open_date).days < 60:
            failed.append("account has been open fewer than 60 days")

    amount = data.get("transaction_amount")
    card_type = data.get("card_type")
    if not number(amount):
        missing.append("numeric transaction_amount")
    if card_type not in TIER_LIMITS:
        missing.append("recognized card_type")
    if number(amount) and card_type in TIER_LIMITS:
        if float(amount) < 25:
            failed.append("transaction amount is below $25.00")
        elif float(amount) > TIER_LIMITS[card_type]:
            failed.append("transaction amount exceeds the card tier limit")

    count = data.get("prior_dispute_count_12_months")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        missing.append("nonnegative prior_dispute_count_12_months")
    elif count > 2:
        failed.append("more than two disputes were filed in the prior 12 months")

    contacted = dispute.get("contacted_merchant")
    if reason != "unauthorized_fraudulent_charge" and contacted is not True:
        # False is a known failure; a malformed/missing field is handled structurally too.
        if contacted is False:
            failed.append("merchant was not contacted for a non-fraud dispute")

    if reason == "goods_services_not_received":
        if as_of and purchase_date:
            age = (as_of - purchase_date).days
            if age <= 30:
                failed.append("goods/services-not-received purchase is not more than 30 days old")
        else:
            missing.append("valid purchase_date and as_of_date to measure the 30-day period")

    # One known failed condition is sufficient for an accurate false determination.
    if failed:
        return False, failed, missing
    if missing:
        return None, failed, missing
    return True, failed, missing


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"valid_for_submission": False, "errors": [f"invalid JSON: {exc.msg}"]}))
        return
    if not isinstance(data, dict) or not isinstance(data.get("dispute"), dict):
        print(json.dumps({"valid_for_submission": False, "errors": ["input must be an object with a dispute object"]}))
        return

    dispute = dict(data["dispute"])
    errors = []
    required_strings = [
        "transaction_id", "card_action", "card_last_4_digits", "full_name", "user_id",
        "phone", "email", "address", "purchase_date", "issue_noticed_date",
        "dispute_reason", "resolution_requested",
    ]
    for field in required_strings:
        if not isinstance(dispute.get(field), str) or not dispute[field].strip():
            errors.append(f"{field} is required and must be a nonempty string")
    if dispute.get("card_action") not in ACTIONS:
        errors.append("card_action must be keep_active or cancel_and_reissue")
    if isinstance(dispute.get("card_last_4_digits"), str) and not (len(dispute["card_last_4_digits"]) == 4 and dispute["card_last_4_digits"].isdigit()):
        errors.append("card_last_4_digits must be exactly four digits")
    if not isinstance(dispute.get("contacted_merchant"), bool):
        errors.append("contacted_merchant must be boolean")
    purchase_date = parse_date(dispute.get("purchase_date"), "purchase_date", errors)
    parse_date(dispute.get("issue_noticed_date"), "issue_noticed_date", errors)
    if dispute.get("dispute_reason") not in REASONS:
        errors.append("dispute_reason is not an allowed code")
    if dispute.get("resolution_requested") not in RESOLUTIONS:
        errors.append("resolution_requested is not an allowed code")

    is_partial = dispute.get("resolution_requested") == "partial_refund"
    partial = dispute.get("partial_refund_amount")
    if is_partial:
        if not number(partial) or float(partial) <= 0:
            errors.append("partial_refund_amount must be a positive number for partial_refund")
    elif partial is not None:
        errors.append("partial_refund_amount must be omitted unless resolution_requested is partial_refund")

    eligible, failed, missing = eligibility(data, dispute, purchase_date)
    supplied = dispute.get("eligible_for_provisional_credit")
    if supplied is not None and not isinstance(supplied, bool):
        errors.append("eligible_for_provisional_credit must be boolean when supplied")
    if eligible is None:
        errors.append("provisional-credit eligibility is indeterminate; collect required eligibility facts")
    elif isinstance(supplied, bool) and supplied != eligible:
        errors.append("supplied eligible_for_provisional_credit conflicts with calculated eligibility")

    tool_arguments = None
    if not errors and eligible is not None:
        tool_arguments = {k: v for k, v in dispute.items() if k != "eligible_for_provisional_credit"}
        tool_arguments["eligible_for_provisional_credit"] = eligible

    result = {
        "valid_for_submission": tool_arguments is not None,
        "errors": errors,
        "eligibility": {
            "determinate": eligible is not None,
            "eligible": eligible,
            "failed_criteria": failed,
            "missing_inputs": sorted(set(missing)),
        },
    }
    if tool_arguments is not None:
        result["tool_arguments"] = tool_arguments
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
