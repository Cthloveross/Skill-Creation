#!/usr/bin/env python3
"""Rank supported business-referral programs from JSON on stdin.

This calculator is informational. It makes no bank calls and does not submit referrals.
"""
import json
import sys

PRODUCTS = [
    {"name": "World Blue", "bonus": 300, "deposit": 25000, "window_days": 90, "tenure_days": 90, "annual_cap": 12},
    {"name": "True Blue", "bonus": 350, "deposit": 50000, "window_days": 120, "tenure_days": 90, "annual_cap": 15},
    {"name": "Beige", "bonus": 500, "deposit": 100000, "window_days": 120, "tenure_days": 120, "annual_cap": 15},
    {"name": "Lime Green", "bonus": 200, "deposit": 15000, "window_days": 90, "tenure_days": 90, "annual_cap": 12},
    {"name": "Hunter Green", "bonus": 175, "deposit": 10000, "window_days": 90, "tenure_days": 60, "annual_cap": 10},
    {"name": "Navy Blue", "bonus": 100, "deposit": 5000, "window_days": 90, "tenure_days": 60, "annual_cap": 10},
    {"name": "Cobalt Blue", "bonus": 150, "deposit": 7500, "window_days": 90, "tenure_days": 60, "annual_cap": None},
]
INCOMPLETE = {
    "name": "Sky Blue",
    "bonus": 150,
    "annual_cap": 8,
    "reason": "Supplied terms do not state a qualifying deposit, deposit window, or referrer tenure."
}


def issue(product, code, detail):
    return {"product": product["name"], "reason_code": code, "detail": detail}


def main(data):
    deposit = data.get("planned_deposit")
    if not isinstance(deposit, (int, float)) or isinstance(deposit, bool) or deposit < 0:
        raise ValueError("planned_deposit must be a non-negative number")

    tenure = data.get("referrer_tenure_days")
    if tenure is not None and (not isinstance(tenure, int) or isinstance(tenure, bool) or tenure < 0):
        raise ValueError("referrer_tenure_days must be a non-negative integer or null")
    rolling = data.get("bonuses_in_last_9_days")
    if rolling is not None and (not isinstance(rolling, int) or isinstance(rolling, bool) or rolling < 0):
        raise ValueError("bonuses_in_last_9_days must be a non-negative integer or null")
    annual = data.get("annual_completed_by_product", {})
    if not isinstance(annual, dict):
        raise ValueError("annual_completed_by_product must be an object")

    result = {"eligible_ranked": [], "blocked": [], "unknown": [], "common_conditions": [
        "The qualifying deposit must be new money, not a transfer from another Rho-Bank account.",
        "The qualifying deposit must remain for at least 30 days after the qualification period ends.",
        "Both accounts must remain in good standing; a referred account closed within 90 days may cause clawback.",
        "At most two referral bonuses may be received in any rolling nine-day window across checking products."
    ]}

    if data.get("common_eligibility_confirmed") is not True:
        result["unknown"].append({"product": "All programs", "reason_code": "COMMON_ELIGIBILITY_UNCONFIRMED", "detail": "The referred party's new-customer, different-address, and different-business-primary-owner facts are not confirmed."})
        result["unknown"].append(INCOMPLETE)
        return result
    if rolling is None:
        result["unknown"].append({"product": "All programs", "reason_code": "ROLLING_CAP_UNKNOWN", "detail": "The number of referral bonuses received in the last nine days is unknown."})
        result["unknown"].append(INCOMPLETE)
        return result
    if rolling >= 2:
        result["blocked"].append({"product": "All programs", "reason_code": "ROLLING_CAP_REACHED", "detail": "Two or more referral bonuses were received in the rolling nine-day window."})
        result["unknown"].append(INCOMPLETE)
        return result

    for product in PRODUCTS:
        if deposit < product["deposit"]:
            result["blocked"].append(issue(product, "DEPOSIT_TOO_LOW", "Planned deposit is below the required qualifying deposit."))
            continue
        if tenure is None:
            result["unknown"].append(issue(product, "TENURE_UNKNOWN", "Earliest checking-account tenure is not known."))
            continue
        if tenure < product["tenure_days"]:
            result["blocked"].append(issue(product, "TENURE_TOO_SHORT", "Earliest checking-account tenure is below this program's threshold."))
            continue
        cap = product["annual_cap"]
        count = annual.get(product["name"])
        if cap is not None:
            if count is None:
                result["unknown"].append(issue(product, "ANNUAL_COUNT_UNKNOWN", "Completed referral-bonus count for this product is unknown."))
                continue
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError("annual product counts must be non-negative integers or omitted")
            if count >= cap:
                result["blocked"].append(issue(product, "ANNUAL_CAP_REACHED", "The stated annual bonus limit has been reached."))
                continue
        result["eligible_ranked"].append({
            "product": product["name"], "referrer_bonus": product["bonus"],
            "required_deposit": product["deposit"], "deposit_window_days": product["window_days"],
            "required_referrer_tenure_days": product["tenure_days"], "annual_cap": cap
        })

    result["eligible_ranked"].sort(key=lambda x: (-x["referrer_bonus"], x["required_deposit"], x["product"]))
    result["unknown"].append(INCOMPLETE)
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
