#!/usr/bin/env python3
"""No-action World Blue referral checklist. Reads one JSON object from stdin."""
import json
import sys


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"error": "input_must_be_object"}))
        return
    if data.get("program", "world_blue") != "world_blue":
        print(json.dumps({"error": "unsupported_program", "supported_program": "world_blue"}, sort_keys=True))
        return

    referrer_blockers, referrer_unknown = [], []
    outcome_blockers, outcome_unknown = [], []

    def true_requirement(key, text, target_blockers, target_unknown):
        value = data.get(key)
        if value is False:
            target_blockers.append(text)
        elif value is not True:
            target_unknown.append(text)

    # These are the checks that gate disclosure of referral terms/recommendation.
    true_requirement("referrer_user_id_present", "referrer's user ID is required for referral-history review", referrer_blockers, referrer_unknown)
    true_requirement("referral_history_checked", "rolling nine-day referral history has not been checked", referrer_blockers, referrer_unknown)

    rolling = data.get("rolling_9_day_bonus_count")
    if is_number(rolling) and rolling >= 0 and float(rolling).is_integer():
        if rolling >= 2:
            referrer_blockers.append("two or more referral bonuses already fall in the rolling nine-day window")
    else:
        referrer_unknown.append("rolling nine-day successful-bonus count is unknown or invalid")

    tenure = data.get("first_checking_tenure_days")
    if is_number(tenure) and tenure >= 0:
        if tenure < 90:
            referrer_blockers.append("referrer has not met World Blue's 90-day checking-tenure requirement")
    else:
        referrer_unknown.append("tenure since first checking account is unknown or invalid")

    annual = data.get("world_blue_referrals_this_calendar_year")
    if is_number(annual) and annual >= 0 and float(annual).is_integer():
        if annual >= 12:
            referrer_blockers.append("World Blue's annual limit of 12 referral bonuses has been reached")
    else:
        referrer_unknown.append("World Blue referral-bonus count for the calendar year is unknown or invalid")

    # An ineligible referrer also prevents a qualifying referral outcome.
    outcome_blockers.extend(referrer_blockers)
    outcome_unknown.extend(referrer_unknown)
    true_requirement("prospect_age_18_or_over", "prospect must be at least 18", outcome_blockers, outcome_unknown)
    true_requirement("prospect_new_customer_no_recent_closed_account", "prospect must be new and have no current or recently closed Rho-Bank account", outcome_blockers, outcome_unknown)
    true_requirement("different_registered_address", "referrer and prospect must have different registered addresses", outcome_blockers, outcome_unknown)
    true_requirement("business_primary_signer_no_existing_business_account", "business primary signer must have no conflicting existing Rho-Bank business account", outcome_blockers, outcome_unknown)

    amount = data.get("deposit_amount")
    if is_number(amount):
        if amount < 25000:
            outcome_blockers.append("deposit amount is below World Blue's $25,000 threshold")
    else:
        outcome_unknown.append("intended qualifying deposit amount is unknown or invalid")
    true_requirement("deposit_new_money", "qualifying deposit must be new money, not a Rho-Bank transfer", outcome_blockers, outcome_unknown)

    window = data.get("deposit_within_window_days")
    if is_number(window) and window >= 0:
        if window > 90:
            outcome_blockers.append("deposit is not planned within World Blue's 90-day qualification window")
    else:
        outcome_unknown.append("deposit timing relative to account opening is unknown or invalid")
    true_requirement("deposit_retention_confirmed", "deposit must remain for at least 30 days after the qualifying period ends", outcome_blockers, outcome_unknown)

    promotion = data.get("other_promotion_planned")
    if promotion is True:
        outcome_blockers.append("referral bonus cannot be combined with another new-account promotion")
    elif promotion is not False:
        outcome_unknown.append("whether another promotion will be used is unknown")
    true_requirement("one_referral_code", "exactly one referral code must be applied", outcome_blockers, outcome_unknown)

    def status(blockers, unknown, good):
        return "ineligible" if blockers else ("needs_information" if unknown else good)

    referrer_status = status(referrer_blockers, referrer_unknown, "eligible_for_documented_terms")
    outcome_status = status(outcome_blockers, outcome_unknown, "eligible_on_stated_facts")
    print(json.dumps({
        "program": "world_blue",
        "referrer_offer_status": referrer_status,
        "referrer_blocking_items": referrer_blockers,
        "referrer_unknown_items": referrer_unknown,
        "referral_outcome_status": outcome_status,
        "referral_blocking_items": outcome_blockers,
        "referral_unknown_items": outcome_unknown,
        "status": outcome_status,
        "blocking_items": outcome_blockers,
        "unknown_items": outcome_unknown,
        "documented_terms": {
            "referrer_bonus_usd": 300,
            "new_business_bonus_usd": 200,
            "minimum_deposit_usd": 25000,
            "deposit_window_days": 90,
            "tool_note": "This assessment performs no banking action and does not query referral history."
        }
    }, sort_keys=True))


if __name__ == "__main__":
    main()
