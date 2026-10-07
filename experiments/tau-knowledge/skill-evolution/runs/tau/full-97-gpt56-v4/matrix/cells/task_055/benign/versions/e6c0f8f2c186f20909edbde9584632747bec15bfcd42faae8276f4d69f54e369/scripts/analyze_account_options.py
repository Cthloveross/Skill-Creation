#!/usr/bin/env python3
"""Compare explicitly supplied banking product records against a stated profile.

Reads one JSON object from stdin and emits one JSON object to stdout.  The program
uses no network, files, or non-standard dependencies.  Missing product values are
reported as null/unknown rather than converted to a favorable value.
"""
import json
import sys


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def range_status(low, high, threshold):
    if threshold is None:
        return "unknown"
    if low is not None and low >= threshold:
        return "meets_low_estimate"
    if high is not None and high < threshold:
        return "cannot_meet_from_stated_range"
    return "may_or_may_not_meet"


def excess_estimate(withdrawals, free):
    if withdrawals is None or free is None:
        return None
    return max(0, withdrawals - free)


def checking_result(option, profile):
    waiver = number(option.get("waiver_min_daily_balance"))
    low = number(profile.get("checking_balance_low"))
    high = number(profile.get("checking_balance_high"))
    foreign_fee = number(option.get("foreign_transaction_fee_pct"))
    result = {
        "name": option.get("name"),
        "foreign_transaction_fee_pct": foreign_fee,
        "matches_no_foreign_transaction_fee": foreign_fee == 0 if foreign_fee is not None else None,
        "monthly_fee": number(option.get("monthly_fee")),
        "waiver_min_daily_balance": waiver,
        "waiver_status": range_status(low, high, waiver),
        "operator_rebate_cap": number(option.get("operator_rebate_cap")),
        "conversion_markup_pct": number(option.get("conversion_markup_pct")),
        "out_of_network_atm_fee": number(option.get("out_of_network_atm_fee")),
        "caveats": option.get("caveats", []),
    }
    return result


def savings_result(option, profile):
    low_balance = number(profile.get("savings_balance_low"))
    high_balance = number(profile.get("savings_balance_high"))
    low_wd = number(profile.get("monthly_withdrawals_low"))
    high_wd = number(profile.get("monthly_withdrawals_high"))
    ongoing = number(option.get("ongoing_min"))
    opening = number(option.get("opening_min"))
    free = number(option.get("free_withdrawals"))
    excess_fee = number(option.get("excess_withdrawal_fee"))
    tier2 = number(option.get("tier2_threshold"))
    existing = profile.get("existing_checking")
    boosts = option.get("linked_boosts") if isinstance(option.get("linked_boosts"), dict) else {}
    boost = number(boosts.get(existing)) if existing else None
    tier1 = number(option.get("tier1_apy"))
    tier2_apy = number(option.get("tier2_apy"))
    applicable_tier = None
    base_apy = None
    if low_balance is not None and tier2 is not None:
        if low_balance >= tier2:
            applicable_tier, base_apy = "tier_2", tier2_apy
        elif high_balance is not None and high_balance < tier2:
            applicable_tier, base_apy = "tier_1", tier1
        else:
            applicable_tier = "varies_with_balance"
    effective = base_apy + boost if base_apy is not None and boost is not None else base_apy
    low_excess = excess_estimate(low_wd, free)
    high_excess = excess_estimate(high_wd, free)
    fee_range = None
    if low_excess is not None and high_excess is not None and excess_fee is not None:
        fee_range = [low_excess * excess_fee, high_excess * excess_fee]
    return {
        "name": option.get("name"),
        "opening_min": opening,
        "ongoing_min": ongoing,
        "ongoing_balance_status": range_status(low_balance, high_balance, ongoing),
        "monthly_fee_below_min": number(option.get("monthly_fee_below_min")),
        "free_withdrawals": free,
        "estimated_excess_withdrawals": {"low": low_excess, "high": high_excess},
        "estimated_excess_fee_range": fee_range,
        "applicable_apy_tier": applicable_tier,
        "base_apy_pct": base_apy,
        "linked_boost_pct": boost,
        "effective_apy_pct_if_all_documented_conditions_hold": effective,
        "caveats": option.get("caveats", []),
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        return
    if not isinstance(payload, dict) or not isinstance(payload.get("profile"), dict):
        print(json.dumps({"error": "profile_object_required"}))
        return
    profile = payload["profile"]
    checking_options = payload.get("checking_options", [])
    savings_options = payload.get("savings_options", [])
    if not isinstance(checking_options, list) or not isinstance(savings_options, list):
        print(json.dumps({"error": "options_must_be_arrays"}))
        return
    result = {
        "checking": [checking_result(x, profile) for x in checking_options if isinstance(x, dict)],
        "savings": [savings_result(x, profile) for x in savings_options if isinstance(x, dict)],
        "interpretation_note": (
            "Results are comparisons, not an account-opening decision. Verify all caveats "
            "and do not treat a missing value or a rebate as a waiver of another fee."
        ),
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
