#!/usr/bin/env python3
"""Referral recommendation planner. Reads one JSON object from stdin and emits one JSON object."""
import json
import sys
from functools import lru_cache
from datetime import date, datetime

PROGRAMS = [
    {"name":"Blue Account","kind":"personal","min_age":18,"referrer_bonus":35,"referred_bonus":30,"cap":5,"deposit":500,"window":60,"tenure":30},
    {"name":"Light Blue Account","kind":"personal","min_age":18,"referrer_bonus":30,"referred_bonus":20,"cap":5,"deposit":500,"window":60,"tenure":30},
    {"name":"Green Fee-Free Account","kind":"personal","min_age":18,"referrer_bonus":20,"referred_bonus":35,"cap":4,"deposit":300,"window":60,"tenure":30},
    {"name":"Light Green Account","kind":"personal","referrer_bonus":15,"referred_bonus":25,"cap":3,"deposit":100,"window":90,"tenure":14,"min_age":13,"max_age":24},
    {"name":"Dark Green Account","kind":"personal","min_age":18,"referrer_bonus":40,"referred_bonus":30,"cap":6,"deposit":1000,"window":60,"tenure":45},
    {"name":"Gold Years Account","kind":"personal","referrer_bonus":50,"referred_bonus":75,"cap":6,"deposit":1000,"window":90,"tenure":30,"min_age":62},
    {"name":"Bluest Account","kind":"personal","min_age":18,"referrer_bonus":75,"referred_bonus":50,"cap":8,"deposit":2000,"window":90,"tenure":60},
    {"name":"Navy Blue Account","kind":"business","referrer_bonus":100,"referred_bonus":75,"cap":10,"deposit":5000,"window":90,"tenure":60},
    {"name":"Sky Blue Account","kind":"business","referrer_bonus":150,"referred_bonus":250,"cap":8,"deposit":10000,"window":90,"tenure":45,"max_company_age":4},
    {"name":"Lime Green Account","kind":"business","referrer_bonus":200,"referred_bonus":150,"cap":12,"deposit":15000,"window":90,"tenure":90},
    {"name":"True Blue Account","kind":"business","referrer_bonus":350,"referred_bonus":250,"cap":15,"deposit":50000,"window":120,"tenure":90},
    {"name":"Beige Account","kind":"business","referrer_bonus":500,"referred_bonus":350,"cap":15,"deposit":100000,"window":120,"tenure":120},
]

def parse_day(value):
    """Accept the ISO dates in the Skill schema and normal tool-style dates."""
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            # Both accepted date forms occupy the first ten characters.
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
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
    # Minors may be referred only to Light Green and only with a guardian.
    if candidate.get("kind") == "personal" and candidate.get("age") is not None and candidate.get("age") < 18:
        fields.append(("has_guardian", "guardian for a minor Light Green applicant"))
    return [label for key, label in fields if candidate.get(key) is not True]

def option_reasons(program, candidate, used, referrer):
    """Return known disqualifiers only; unknown facts remain explicit conditions."""
    reasons = []
    if candidate.get("kind") != program.get("kind"):
        reasons.append("account type does not match personal/business need")
    # Do not treat a known failure as merely an unverified condition.  These
    # restrictions apply to every checking-referral program.
    if candidate.get("new_customer") is False:
        reasons.append("recipient is not a new Rho-Bank customer or had an account closed within the prior 12 months")
    if candidate.get("different_address") is False:
        reasons.append("recipient has the same registered address as the referrer")
    if candidate.get("kind") == "business" and candidate.get("different_primary_owner") is False:
        reasons.append("business has the same primary owner/authorized signer as an existing Rho-Bank business account")
    if (program["name"] == "Light Green Account" and candidate.get("age") is not None
            and candidate.get("age") < 18 and candidate.get("has_guardian") is False):
        reasons.append("minor Light Green applicant does not have a guardian")
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
    ]
    if "min_age" in program:
        required.append("recipient is at least {} years old".format(program["min_age"]))
    if "max_age" in program:
        required.append("recipient is no more than {} years old".format(program["max_age"]))
    if program["name"] == "Light Green Account" and candidate.get("age") is not None and candidate.get("age") < 18:
        required.append("minor applicant has a guardian")
    if "max_company_age" in program:
        required.append("business was formed within {} years".format(program["max_company_age"]))
    required += common_conditions(candidate)
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

def select_plan(candidates, programs, used, referrer, as_of):
    """Choose a cap-feasible assignment maximizing stated combined incentive.

    The result is in candidate order.  During the documented promotion, a
    business candidate is limited to its highest-priority qualifying tier
    before bonus amounts are compared.  This preserves the promotion rule
    while avoiding a greedy choice that can waste the final annual slot a
    later candidate uniquely needs.
    """
    choices, rejected_by_candidate = [], []
    for candidate in candidates:
        viable, rejected = [], []
        for index, program in enumerate(programs):
            reasons = option_reasons(program, candidate, used, referrer)
            if reasons:
                rejected.append({"account": program["name"], "reasons": reasons})
            else:
                viable.append(index)
        if viable and candidate.get("kind") == "business" and as_of.year == 2025 and as_of.month == 11:
            best_rank = min(promotion_rank(programs[i], as_of, candidate) for i in viable)
            viable = [i for i in viable if promotion_rank(programs[i], as_of, candidate) == best_rank]
        choices.append(tuple(viable))
        rejected_by_candidate.append(rejected)

    initial_remaining = tuple(max(0, program["cap"] - used.get(program["name"], 0)) for program in programs)

    @lru_cache(maxsize=None)
    def solve(candidate_index, remaining):
        if candidate_index == len(candidates):
            return (0, 0, ())
        # No selection is permitted if every candidate-specific option is
        # unavailable.  Otherwise all stated bonuses are positive, so a
        # selection will beat this fallback when capacity permits.
        best = solve(candidate_index + 1, remaining)
        best = (best[0], best[1], (None,) + best[2])
        for program_index in choices[candidate_index]:
            if remaining[program_index] <= 0:
                continue
            next_remaining = list(remaining)
            next_remaining[program_index] -= 1
            tail = solve(candidate_index + 1, tuple(next_remaining))
            program = programs[program_index]
            value = (tail[0] + program["referrer_bonus"] + program["referred_bonus"],
                     tail[1] + program["referrer_bonus"],
                     (program_index,) + tail[2])
            # Stable ties use the catalog order rather than incidental input
            # ordering.  Compare only monetary objectives here; an exact tie
            # is resolved by retaining the first program encountered.
            if value[:2] > best[:2]:
                best = value
        return best

    _, _, selected = solve(0, initial_remaining)
    return selected, rejected_by_candidate

def main(data):
    as_of = parse_day(data.get("as_of"))
    if not as_of:
        raise ValueError("as_of must be YYYY-MM-DD")
    referrer = dict(data.get("referrer") or {})
    # Callers may supply either a calculated tenure or the actual first
    # checking opening date obtained at runtime.  The latter is calculated
    # against as_of so account type never substitutes for tenure.
    if referrer.get("tenure_days") is None:
        opened = parse_day(referrer.get("first_checking_opened"))
        if opened and opened <= as_of:
            referrer["tenure_days"] = (as_of - opened).days
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
    eligible_now = not gate_missing
    # Eligibility is a mandatory gate for every referral program.  Do not
    # disclose program terms or turn uncertain eligibility into a conditional
    # recommendation: a customer's request for a conditional answer cannot
    # override the prerequisite.
    if not eligible_now:
        return {
            "eligible_now": False,
            "conditional": False,
            "stop_before_terms": True,
            "missing_eligibility_gate_facts": gate_missing,
            "annual_cap_usage": used,
            "recent_complete_bonus_count": recent_complete,
            "message": "Obtain the missing referrer eligibility facts before discussing referral terms or recommendations."
        }

    conditional = False
    candidates = data.get("candidates", [])
    selected, rejected_by_candidate = select_plan(candidates, programs, used, referrer, as_of)
    recommendations, unavailable = [], []
    planned = dict(used)
    for candidate, program_index, rejected in zip(candidates, selected, rejected_by_candidate):
        if program_index is None:
            unavailable.append({
                "recipient": candidate.get("label", "unnamed recipient"),
                "reason": "No supplied program meets the known facts and remaining annual caps.",
                "program_results": rejected,
            })
            continue
        chosen = programs[program_index]
        planned[chosen["name"]] = planned.get(chosen["name"], 0) + 1
        item = describe(chosen, candidate, referrer, conditional)
        item["recipient"] = candidate.get("label", "unnamed recipient")
        recommendations.append(item)

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
