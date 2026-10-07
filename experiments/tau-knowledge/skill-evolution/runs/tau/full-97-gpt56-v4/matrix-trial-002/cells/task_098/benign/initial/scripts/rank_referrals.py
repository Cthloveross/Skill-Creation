#!/usr/bin/env python3
"""Rank Rho-Bank checking referral offers from JSON stdin.

Input schema is documented in SKILL.md. This script performs no banking action and
never reads customer data except what the caller provides on stdin.
"""
import json
import sys
from datetime import datetime, timedelta

PRODUCTS = [
    {"account": "Blue Account", "referrer_bonus": 35, "new_member_bonus": 30,
     "annual_cap": 5, "deposit": 500, "deposit_days": 60, "tenure_days": 30},
    {"account": "Green Fee-Free Account", "referrer_bonus": 20, "new_member_bonus": 35,
     "annual_cap": 4, "deposit": 300, "deposit_days": 60, "tenure_days": 30},
    {"account": "Light Blue Account", "referrer_bonus": 30, "new_member_bonus": 20,
     "annual_cap": 5, "deposit": 500, "deposit_days": 60, "tenure_days": 30},
    {"account": "Light Green Account", "referrer_bonus": 15, "new_member_bonus": 25,
     "annual_cap": 3, "deposit": 100, "deposit_days": 90, "tenure_days": 14,
     "min_age": 13, "max_age": 24, "minor_guardian_required": True},
    {"account": "Dark Green Account", "referrer_bonus": 40, "new_member_bonus": 30,
     "annual_cap": 6, "deposit": 1000, "deposit_days": 60, "tenure_days": 45},
    {"account": "Bluest Account", "referrer_bonus": 75, "new_member_bonus": 50,
     "annual_cap": 8, "deposit": 2000, "deposit_days": 90, "tenure_days": 60},
    {"account": "Gold Years Account", "referrer_bonus": 50, "new_member_bonus": 75,
     "annual_cap": 6, "deposit": 1000, "deposit_days": 90, "tenure_days": 30,
     "min_age": 62},
]


def parse_time(value):
    """Return (datetime, date_only), or (None, False)."""
    if not isinstance(value, str) or not value.strip():
        return None, False
    text = value.strip()
    # Tool output may include a simple trailing timezone label; comparisons are local.
    parts = text.split()
    if len(parts) == 3 and parts[-1].isalpha():
        text = " ".join(parts[:-1])
    try:
        if len(text) == 10:
            return datetime.strptime(text, "%Y-%m-%d"), True
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None), False
    except ValueError:
        for fmt in ("%m/%d/%Y", "%m/%d/%Y %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt), fmt == "%m/%d/%Y"
            except ValueError:
                pass
    return None, False


def offer_view(product):
    return {
        "account": product["account"],
        "referrer_bonus": product["referrer_bonus"],
        "new_member_bonus": product["new_member_bonus"],
        "combined_bonus": product["referrer_bonus"] + product["new_member_bonus"],
        "required_deposit": product["deposit"],
        "deposit_deadline_days": product["deposit_days"],
        "required_referrer_tenure_days": product["tenure_days"],
        "annual_cap": product["annual_cap"],
    }


def main(data):
    now, _ = parse_time(data.get("current_time"))
    if now is None:
        return {"error": "current_time is required and must be a parseable timestamp"}

    baseline_issues = []
    for key, label in (
        ("is_new_customer_no_recent_account", "new-customer/no-recent-account status"),
        ("different_registered_address", "different registered-address status"),
    ):
        val = data.get(key)
        if val is not True:
            baseline_issues.append(label + (" is not satisfied" if val is False else " is unknown"))

    age = data.get("referred_age")
    if not isinstance(age, int) or isinstance(age, bool):
        age = None
    guardian = data.get("guardian_participates") is True
    deposit = data.get("expected_deposit")
    if not isinstance(deposit, (int, float)) or isinstance(deposit, bool):
        deposit = None
    tenure = data.get("referrer_tenure_days")
    if not isinstance(tenure, (int, float)) or isinstance(tenure, bool):
        tenure = None

    referrals = data.get("referrals") if isinstance(data.get("referrals"), list) else []
    completed = [r for r in referrals if isinstance(r, dict) and r.get("referral_status") == "COMPLETE"]
    cutoff = now - timedelta(days=9)
    definite_rolling = 0
    uncertain_rolling = 0
    malformed_completed = 0
    for record in completed:
        moment, date_only = parse_time(record.get("timestamp", record.get("date")))
        if moment is None:
            malformed_completed += 1
            continue
        if not date_only:
            if moment >= cutoff:
                definite_rolling += 1
        else:
            # A date covers [midnight, next midnight), so classify only when certain.
            if moment >= cutoff:
                definite_rolling += 1
            elif moment + timedelta(days=1) > cutoff:
                uncertain_rolling += 1
    rolling_status = {
        "window_start": cutoff.strftime("%Y-%m-%d %H:%M:%S"),
        "completed_bonuses_definitely_in_window": definite_rolling,
        "borderline_date_only_completed_bonuses": uncertain_rolling,
        "completed_records_with_unparseable_time": malformed_completed,
    }
    if definite_rolling >= 2:
        baseline_issues.append("rolling 9-day successful-referral limit has been reached")
    elif definite_rolling + uncertain_rolling >= 2 or malformed_completed:
        baseline_issues.append("rolling 9-day limit cannot be confirmed from available referral timestamps")

    eligible, blocked, unresolved = [], [], []
    year = now.year
    for product in PRODUCTS:
        item = offer_view(product)
        reasons = []
        unknown = []
        if deposit is None:
            unknown.append("expected deposit is unknown")
        elif deposit < product["deposit"]:
            reasons.append("expected deposit is below required deposit")
        if tenure is None:
            unknown.append("referrer tenure is unknown")
        elif tenure < product["tenure_days"]:
            reasons.append("referrer tenure is below required minimum")

        if product["account"] == "Light Green Account":
            if age is None:
                unknown.append("age is required for Light Green eligibility")
            elif age < 13 or age > 24:
                reasons.append("prospective holder is outside Light Green's 13–24 age range")
            elif age < 18 and not guardian:
                reasons.append("an eligible Light Green minor needs guardian participation")
        elif product["account"] == "Gold Years Account":
            if age is None:
                unknown.append("age is required for Gold Years eligibility")
            elif age < 62:
                reasons.append("prospective holder is younger than 62")
        else:
            if age is None:
                unknown.append("age is required to confirm standard adult eligibility")
            elif age < 18:
                reasons.append("standard referral programs require a prospective customer age 18 or older")

        annual_count = 0
        for record in completed:
            if record.get("referred_account_type") != product["account"]:
                continue
            moment, _ = parse_time(record.get("timestamp", record.get("date")))
            if moment is not None and moment.year == year:
                annual_count += 1
        item["completed_referrals_this_calendar_year_for_account"] = annual_count
        if annual_count >= product["annual_cap"]:
            reasons.append("annual referral-bonus cap for this account has been reached")

        if baseline_issues:
            reasons.extend(baseline_issues)
        if reasons:
            item["reasons"] = sorted(set(reasons))
            blocked.append(item)
        elif unknown:
            item["missing_facts"] = sorted(set(unknown))
            unresolved.append(item)
        else:
            eligible.append(item)

    eligible.sort(key=lambda x: (-x["combined_bonus"], x["account"]))
    blocked.sort(key=lambda x: (-x["combined_bonus"], x["account"]))
    unresolved.sort(key=lambda x: (-x["combined_bonus"], x["account"]))
    recommendation = eligible[0] if eligible else None
    return {
        "recommendation": recommendation,
        "eligible_offers": eligible,
        "blocked_offers": blocked,
        "unresolved_offers": unresolved,
        "baseline_issues": sorted(set(baseline_issues)),
        "rolling_window": rolling_status,
        "universal_conditions": [
            "Qualifying deposit must be new money and not a transfer from another Rho-Bank account.",
            "Qualifying deposit must remain for at least 30 days after the qualifying period ends.",
            "Only one referral code and no other new-account promotion may be applied.",
            "Both accounts must remain in good standing; closure within 90 days may trigger a clawback.",
        ],
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
