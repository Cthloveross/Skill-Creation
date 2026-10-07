#!/usr/bin/env python3
"""Referral recommendation planner. Reads one JSON object from stdin and emits one JSON object."""
import json
import sys
from datetime import date, datetime

PROGRAMS = [
    {"name":"Blue Account","kind":"personal","referrer_bonus":35,"referred_bonus":30,"cap":5,"deposit":500,"window":60,"tenure":30},
    {"name":"Light Blue Account","kind":"personal","referrer_bonus":30,"referred_bonus":20,"cap":5,"deposit":500,"window":60,"tenure":30},
    {"name":"Green Fee-Free Account","kind":"personal","referrer_bonus":20,"referred_bonus":35,"cap":4,"deposit":300,"window":60,"tenure":30},
    {"name":"Light Green Account","kind":"personal","referrer_bonus":15,"referred_bonus":25,"cap":3,"deposit":100,"window":90,"tenure":14,"min_age":13,"max_age":24},
    {"name":"Dark Green Account","kind":"personal","referrer_bonus":40,"referred_bonus":30,"cap":6,"deposit":1000,"window":60,"tenure":45},
    {"name":"Gold Years Account","kind":"personal","referrer_bonus":50,"referred_bonus":75,"cap":6,"deposit":1000,"window":90,"tenure":30,"min_age":62},
    {"name":"Bluest Account","kind":"personal","referrer_bonus":75,"referred_bonus":50,"cap":8,"deposit":2000,"window":90,"tenure":60},
    {"name":"Navy Blue Account","kind":"business","referrer_bonus":100,"referred_bonus":75,"cap":10,"deposit":5000,"window":90,"tenure":60},
    {"name":"Sky Blue Account","kind":"business","referrer_bonus":150,"referred_bonus":250,"cap":8,"deposit":10000,"window":90,"tenure":45,"max_company_age":4},
    {"name":"Lime Green Account","kind":"business","referrer_bonus":200,"referred_bonus":150,"cap":12,"deposit":15000,"window":90,"tenure":90},
    {"name":"True Blue Account","kind":"business","referrer_bonus":350,"referred_bonus":250,"cap":15,"deposit":50000,"window":120,"tenure":90},
    {"name":"Beige Account","kind":"business","referrer_bonus":500,"referred_bonus":350,"cap":15,"deposit":100000,"window":120,"tenure":120},
]

def parse_day(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None

def common_conditions(candidate):
    conditions = [
        "recipient is a new Rho-Bank customer with no existing or closed account in the prior 12 months",
        "recipient has a registered address different from the referrer",
        "qualifying deposit is new money, not a transfer from another Rho-Bank account",
        "qualifying deposit remains for at least 30 days after the qualifying period",
        "both accounts remain in good standing",
        "only one referral code is used and no new-account/sign-up promotion is stacked",
    ]
    if candidate.get("kind") == "business":
        conditions.append("business has a primary owner/authorized signer different from any existing Rho-Bank business account")
    return conditions

def stated_unknowns(candidate):
    fields = [("new_customer", "new-customer status"), ("different_address", "different registered address")]
    if candidate.get("kind") == "business":
        fields.append(("different_primary_owner", "different primary owner/authorized signer"))
    return [label for key, label in fields if candidate.get(key) is not True]

def option_reasons(program, candidate, used, referrer):
    reasons = []
    if candidate.get("kind") != program.get("kind"):
        reasons.append("account type does not match personal/business need")
    if candidate.get("deposit") is None or candidate.get("deposit") < program["deposit"]:
        reasons.append("available deposit is below required qualifying deposit")
    age = candidate.get("age")
    if "min_age" in program and (age is None or age < program["min_age"]):
        reasons.append("recipient does not meet minimum age")
    if "max_age" in program and (age is None or age > program["max_age"]):
        reasons.append("recipient exceeds account age limit")
    company_age = candidate.get("company_age_years")
    if "max_company_age" in program and (company_age is None or company_age > program["max_company_age"]):
        reasons.append("business exceeds startup formation-age requirement")
    if used.get(program["name"], 0) >= program["cap"]:
        reasons.append("annual referral-bonus cap has been reached")
    tenure = referrer.get("tenure_days")
    if tenure is not None and tenure < program["tenure"]:
        reasons.append("referrer does not meet required checking tenure")
    if referrer.get("good_standing") is False:
        reasons.append("referrer is not in good standing")
    return reasons

def promotion_rank(program, as_of, candidate):
    # The supplied promotion runs during November 2025 and applies only to business accounts.
    if candidate.get("kind") == "business" and as_of.year == 2025 and as_of.month == 11:
        if program["name"] == "Sky Blue Account": return 0
        if program["name"] == "Lime Green Account": return 1
    return 2

def describe(program, candidate, referrer, conditional):
    required = [
        "deposit at least ${:,.0f} within {} days".format(program["deposit"], program["window"]),
        "referrer has at least {} days since first Rho-Bank checking account opening".format(program["tenure"]),
    ] + common_conditions(candidate)
    unknown = stated_unknowns(candidate)
    if referrer.get("tenure_days") is None:
        unknown.append("referrer first-checking-account tenure")
    if referrer.get("good_standing") is not True:
        unknown.append("referrer good-standing status")
    return {
        "account": program["name"],
        "referrer_bonus": program["referrer_bonus"],
        "referred_bonus": program["referred_bonus"],
        "combined_stated_incentive": program["referrer_bonus"] + program["referred_bonus"],
        "annual_cap": program["cap"],
        "required_conditions": required,
        "unverified_conditions": unknown,
        "conditional": conditional or bool(unknown),
    }

def main(data):
    as_of = parse_day(data.get("as_of"))
    if not as_of:
        raise ValueError("as_of must be YYYY-MM-DD")
    referrer = data.get("referrer") or {}
    programs = data.get("programs") or PROGRAMS
    used = {p["name"]: 0 for p in programs}
    recent_complete = 0
    for row in data.get("existing_referrals", []):
        when = parse_day(row.get("date"))
        account = row.get("account_type")
        if row.get("status") == "COMPLETE" and when and when.year == as_of.year and account in used:
            used[account] += 1
        if row.get("status") == "COMPLETE" and when and 0 <= (as_of - when).days <= 9:
            recent_complete += 1

    gate_missing = []
    if referrer.get("tenure_days") is None:
        gate_missing.append("date of first Rho-Bank checking account opening (or tenure in days)")
    if referrer.get("good_standing") is not True:
        gate_missing.append("confirmation that the referrer's checking relationship is in good standing")
    conditional_allowed = bool(data.get("conditional_allowed"))
    eligible_now = not gate_missing
    if gate_missing and not conditional_allowed:
        return {
            "eligible_now": False,
            "conditional": False,
            "stop_before_terms": True,
            "missing_eligibility_gate_facts": gate_missing,
            "annual_cap_usage": used,
            "recent_complete_bonus_count": recent_complete,
            "message": "Obtain the missing referrer eligibility facts before discussing referral terms or recommendations."
        }

    conditional = not eligible_now
    recommendations, unavailable = [], []
    # Track planned cap usage so recommendations do not collectively exceed a cap.
    planned = dict(used)
    for candidate in data.get("candidates", []):
        viable, rejected = [], []
        for program in programs:
            reasons = option_reasons(program, candidate, planned, referrer)
            if reasons:
                rejected.append({"account": program["name"], "reasons": reasons})
            else:
                viable.append(program)
        if viable:
            viable.sort(key=lambda p: (promotion_rank(p, as_of, candidate), -(p["referrer_bonus"] + p["referred_bonus"]), -p["referrer_bonus"], p["name"]))
            chosen = viable[0]
            planned[chosen["name"]] = planned.get(chosen["name"], 0) + 1
            item = describe(chosen, candidate, referrer, conditional)
            item["recipient"] = candidate.get("label", "unnamed recipient")
            recommendations.append(item)
        else:
            unavailable.append({"recipient": candidate.get("label", "unnamed recipient"), "reason": "No supplied program meets the known facts and remaining annual caps.", "program_results": rejected})

    available_slots_now = max(0, 2 - recent_complete)
    return {
        "eligible_now": eligible_now,
        "conditional": conditional,
        "missing_eligibility_gate_facts": gate_missing,
        "annual_cap_usage_before_plan": used,
        "annual_cap_usage_after_plan": planned,
        "recent_complete_bonus_count": recent_complete,
        "recommendations": recommendations,
        "unavailable": unavailable,
        "rolling_window_plan": {
            "successful_bonus_slots_remaining_in_current_date_based_window": available_slots_now,
            "instruction": "Arrange no more than two successful bonus-qualification events in any rolling nine-day period across all checking products. Dates without timestamps are conservative; wait until older successful bonuses are outside the window before the next group."
        },
        "global_conditions": [
            "A referral bonus cannot be combined with another new-account promotion or sign-up bonus.",
            "An early closure of the referred account within 90 days may cause referral-bonus clawback."
        ]
    }

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), indent=2, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
