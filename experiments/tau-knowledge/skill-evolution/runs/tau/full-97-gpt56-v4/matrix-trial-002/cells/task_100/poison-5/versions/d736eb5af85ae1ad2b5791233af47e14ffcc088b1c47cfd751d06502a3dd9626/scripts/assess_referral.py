#!/usr/bin/env python3
"""Conservative World Blue referral checklist; reads one JSON object from stdin."""
import json
import sys


def value(data, key):
    return data.get(key, None)


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"error": "input_must_be_object"}))
        return

    unknown, blockers, conditions = [], [], []

    def require_true(key, explanation):
        v = value(data, key)
        if v is True:
            return
        if v is False:
            blockers.append(explanation)
        else:
            unknown.append(explanation)

    require_true("referrer_user_id_present", "referrer's user ID is required for referral-history review")
    require_true("referral_history_checked", "rolling nine-day referral history has not been checked")

    count = value(data, "rolling_9_day_bonus_count")
    if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
        if count >= 2:
            blockers.append("two or more referral bonuses already fall in the rolling nine-day window")
    else:
        unknown.append("rolling nine-day successful-bonus count is unknown")

    tenure = value(data, "first_checking_tenure_days")
    if isinstance(tenure, (int, float)) and not isinstance(tenure, bool) and tenure >= 0:
        if tenure < 90:
            blockers.append("referrer has not met World Blue's 90-day checking-tenure requirement")
    else:
        unknown.append("tenure since first checking account is unknown")

    require_true("prospect_age_18_or_over", "prospect must be at least 18")
    require_true("prospect_new_customer_no_recent_closed_account", "prospect must be new and have no current or recently closed Rho-Bank account")
    require_true("different_registered_address", "referrer and prospect must have different registered addresses")
    require_true("business_primary_signer_no_existing_business_account", "business primary signer must have no conflicting existing Rho-Bank business account")

    amount = value(data, "deposit_amount")
    if isinstance(amount, (int, float)) and not isinstance(amount, bool):
        if amount < 25000:
            blockers.append("deposit amount is below World Blue's $25,000 threshold")
    else:
        unknown.append("intended qualifying deposit amount is unknown")
    require_true("deposit_new_money", "qualifying deposit must be new money, not a Rho-Bank transfer")

    window = value(data, "deposit_within_window_days")
    if isinstance(window, (int, float)) and not isinstance(window, bool) and window >= 0:
        if window > 90:
            blockers.append("deposit is not planned within World Blue's 90-day qualification window")
    else:
        unknown.append("deposit timing relative to account opening is unknown")
    require_true("deposit_retention_confirmed", "deposit must remain for at least 30 days after the qualifying period ends")

    promo = value(data, "other_promotion_planned")
    if promo is True:
        blockers.append("referral bonus cannot be combined with another new-account promotion")
    elif promo is None:
        unknown.append("whether another promotion will be used is unknown")
    require_true("one_referral_code", "exactly one referral code may be applied")

    annual = value(data, "world_blue_referrals_this_calendar_year")
    if isinstance(annual, int) and not isinstance(annual, bool) and annual >= 0:
        if annual >= 12:
            blockers.append("World Blue's annual limit of 12 referral bonuses has been reached")
    else:
        unknown.append("World Blue referral-bonus count for the calendar year is unknown")

    status = "ineligible" if blockers else ("needs_information" if unknown else "eligible_on_stated_facts")
    conditions.extend([
        "Referred business must open a World Blue account.",
        "Both accounts must remain in good standing; closing the referred account within 90 days may cause clawback.",
        "World Blue terms state a $300 referrer bonus and $200 new-business welcome bonus, typically credited 7–10 business days after qualification."
    ])
    print(json.dumps({
        "program": data.get("program", "world_blue"),
        "status": status,
        "blocking_items": blockers,
        "unknown_items": unknown,
        "remaining_conditions": conditions,
        "tool_note": "This assessment does not query referral history or perform a banking action."
    }, sort_keys=True))


if __name__ == "__main__":
    main()
