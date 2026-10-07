#!/usr/bin/env python3
"""Optimize a set of referral allocations using packaged referral policies.

Reads the schema documented in SKILL.md from stdin and writes a JSON result to
stdout. It performs no network, banking, or file-changing operations.
"""
import datetime as dt
import json
import sys
from pathlib import Path

POLICY_PATH = Path(__file__).resolve().parents[1] / "references" / "referral_programs.json"


def number(value, field, errors, nonnegative=True):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{field} must be a number")
        return None
    if nonnegative and value < 0:
        errors.append(f"{field} must not be negative")
        return None
    return value


def parse_date(value, field, errors):
    if not isinstance(value, str):
        errors.append(f"{field} must be YYYY-MM-DD")
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        errors.append(f"{field} must be YYYY-MM-DD")
        return None


def current_counts(referrals, year, program_names, errors):
    counts = {name: 0 for name in program_names}
    if not isinstance(referrals, list):
        errors.append("referrals must be a list")
        return counts
    for index, referral in enumerate(referrals):
        if not isinstance(referral, dict):
            errors.append(f"referrals[{index}] must be an object")
            continue
        when = parse_date(referral.get("date"), f"referrals[{index}].date", errors)
        if when is None or when.year != year:
            continue
        status = str(referral.get("referral_status", "")).upper()
        account = referral.get("referred_account_type")
        if status == "COMPLETE" and account in counts:
            counts[account] += 1
    return counts


def eligibility(candidate, program, tenure, good_standing, remaining):
    """Return an ordered list of reasons that an option cannot be confirmed."""
    reasons = []
    name = program["account_type"]
    if remaining.get(name, 0) <= 0:
        reasons.append("annual referral-bonus cap is exhausted")
    if candidate.get("kind") != program["kind"]:
        reasons.append(f"program is for {program['kind']} candidates")
        return reasons

    if program["kind"] == "individual":
        age = candidate.get("age")
        if isinstance(age, bool) or not isinstance(age, (int, float)):
            reasons.append("candidate age is not established")
        else:
            if "age_min" in program and age < program["age_min"]:
                reasons.append(f"candidate is below the minimum age of {program['age_min']}")
            if "age_max" in program and age > program["age_max"]:
                reasons.append(f"candidate is above the maximum age of {program['age_max']}")
    else:
        maximum = program.get("formation_age_years_max")
        if maximum is not None:
            formation_age = candidate.get("formation_age_years")
            if isinstance(formation_age, bool) or not isinstance(formation_age, (int, float)):
                reasons.append("business formation age is not established")
            elif formation_age > maximum:
                reasons.append(f"business is older than the {maximum}-year formation limit")

    minimum_deposit = program["min_deposit"]
    if minimum_deposit > 0:
        amount = candidate.get("deposit_amount")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            reasons.append("qualifying deposit amount is not established")
        elif amount < minimum_deposit:
            reasons.append(f"deposit is below the ${minimum_deposit:,.0f} requirement")

        deadline = program["deposit_window_days"]
        timing_ok = candidate.get("deposit_timing_confirmed") is True
        deposit_days = candidate.get("deposit_within_days")
        if not timing_ok:
            if isinstance(deposit_days, bool) or not isinstance(deposit_days, (int, float)):
                reasons.append(f"ability to deposit within {deadline} days is not established")
            elif deposit_days > deadline:
                reasons.append(f"deposit cannot be made within the {deadline}-day deadline")

    required_tenure = program.get("referrer_tenure_days", 0)
    if required_tenure > 0:
        if isinstance(tenure, bool) or not isinstance(tenure, (int, float)):
            reasons.append(f"referrer checking tenure of {required_tenure} days is not established")
        elif tenure < required_tenure:
            reasons.append(f"referrer has not met the {required_tenure}-day checking-tenure requirement")

    if program.get("requires_good_standing") and good_standing is not True:
        reasons.append("required referrer good-standing status is not established")
    return reasons


def score_for(program, objective):
    referrer = program["referrer_bonus"]
    combined = referrer + program["recipient_bonus"]
    return combined if objective == "combined_bonus" else referrer


def better(candidate_result, incumbent, objective):
    """Stable comparison: objective, then referrer total, combined total, allocations."""
    if incumbent is None:
        return True
    def key(result):
        allocations = sum(1 for item in result["choices"] if item is not None)
        names = tuple("" if item is None else item["account_type"] for item in result["choices"])
        primary = result["combined"] if objective == "combined_bonus" else result["referrer"]
        return (primary, result["referrer"], result["combined"], allocations, tuple(-ord(c) for c in "|".join(names)))
    return key(candidate_result) > key(incumbent)


def optimize(candidates, programs, remaining, tenure, good_standing, objective):
    assessments = []
    eligible_by_candidate = []
    for candidate in candidates:
        options = []
        assessment = {"candidate": candidate.get("name", ""), "programs": []}
        for program in programs:
            reasons = eligibility(candidate, program, tenure, good_standing, remaining)
            row = {
                "account_type": program["account_type"],
                "eligible": not reasons,
                "reasons": reasons,
                "referrer_bonus": program["referrer_bonus"],
                "recipient_bonus": program["recipient_bonus"],
                "combined_bonus": program["referrer_bonus"] + program["recipient_bonus"]
            }
            assessment["programs"].append(row)
            if not reasons:
                options.append(program)
        assessments.append(assessment)
        eligible_by_candidate.append(options)

    best = None
    def visit(index, used, choices, referrer_total, recipient_total):
        nonlocal best
        if index == len(candidates):
            result = {
                "choices": choices[:],
                "referrer": referrer_total,
                "recipient": recipient_total,
                "combined": referrer_total + recipient_total
            }
            if better(result, best, objective):
                best = result
            return
        # An unallocated candidate is always allowed.
        visit(index + 1, used, choices + [None], referrer_total, recipient_total)
        for program in eligible_by_candidate[index]:
            name = program["account_type"]
            if used.get(name, 0) >= remaining[name]:
                continue
            new_used = dict(used)
            new_used[name] = new_used.get(name, 0) + 1
            visit(index + 1, new_used, choices + [program],
                  referrer_total + program["referrer_bonus"],
                  recipient_total + program["recipient_bonus"])
    visit(0, {}, [], 0, 0)
    return best, assessments


def main(payload):
    errors = []
    if not isinstance(payload, dict):
        return {"validation_errors": ["input must be a JSON object"]}
    as_of = parse_date(payload.get("as_of_date"), "as_of_date", errors)
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        errors.append("candidates must be a list")
        candidates = []
    for i, item in enumerate(candidates):
        if not isinstance(item, dict):
            errors.append(f"candidates[{i}] must be an object")
        elif not isinstance(item.get("name"), str) or not item["name"].strip():
            errors.append(f"candidates[{i}].name must be a nonempty string")
        elif item.get("kind") not in ("individual", "business"):
            errors.append(f"candidates[{i}].kind must be individual or business")
    if errors:
        return {"validation_errors": errors}

    policies = json.loads(POLICY_PATH.read_text(encoding="utf-8"))["programs"]
    names = [p["account_type"] for p in policies]
    counts = current_counts(payload.get("referrals"), as_of.year, names, errors)
    if errors:
        return {"validation_errors": errors}
    remaining = {p["account_type"]: max(0, p["annual_cap"] - counts[p["account_type"]]) for p in policies}
    tenure = payload.get("checking_tenure_days")
    if tenure is not None:
        tenure = number(tenure, "checking_tenure_days", errors)
    objective = payload.get("objective", "combined_bonus")
    if objective not in ("combined_bonus", "referrer_bonus"):
        errors.append("objective must be combined_bonus or referrer_bonus")
    if errors:
        return {"validation_errors": errors}

    solution, assessments = optimize(candidates, policies, remaining, tenure,
                                     payload.get("referrer_good_standing"), objective)
    allocation = []
    used = {name: 0 for name in names}
    for candidate, program in zip(candidates, solution["choices"]):
        if program is None:
            allocation.append({"candidate": candidate["name"], "account_type": None,
                               "status": "no confirmed qualifying allocation"})
            continue
        name = program["account_type"]
        used[name] += 1
        allocation.append({
            "candidate": candidate["name"],
            "account_type": name,
            "status": "recommended if all stated facts remain true",
            "referrer_bonus": program["referrer_bonus"],
            "recipient_bonus": program["recipient_bonus"],
            "combined_bonus": program["referrer_bonus"] + program["recipient_bonus"],
            "minimum_deposit": program["min_deposit"],
            "deposit_window_days": program["deposit_window_days"]
        })
    violations = []
    for name, count in used.items():
        if count > remaining[name]:
            violations.append(f"{name} allocation exceeds remaining annual cap")
    return {
        "validation_errors": [],
        "objective": objective,
        "calendar_year": as_of.year,
        "current_completed_counts": counts,
        "remaining_cap_by_program": remaining,
        "candidate_assessments": assessments,
        "allocation": allocation,
        "totals": {
            "referrer_bonus": solution["referrer"],
            "recipient_bonus": solution["recipient"],
            "combined_bonus": solution["combined"]
        },
        "post_allocation_violations": violations
    }


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        print(json.dumps(main(incoming), indent=2, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"validation_errors": [f"invalid JSON input: {exc.msg}"]}))
    except Exception as exc:
        # Preserve a machine-readable failure without claiming a recommendation.
        print(json.dumps({"validation_errors": [f"calculator error: {type(exc).__name__}: {exc}"]}))
