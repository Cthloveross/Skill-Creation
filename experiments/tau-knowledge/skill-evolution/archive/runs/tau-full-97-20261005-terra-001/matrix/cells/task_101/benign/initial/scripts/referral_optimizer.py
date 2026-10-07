#!/usr/bin/env python3
"""Rank documented checking referral programs from a JSON case on stdin."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[1] / "references" / "referral_programs.json"


def parse_time(value):
    """Return (datetime, exact_timestamp) for ISO date/datetime input."""
    if not isinstance(value, str) or not value.strip():
        return None, False
    value = value.strip()
    try:
        if len(value) == 10:
            return datetime.fromisoformat(value).replace(tzinfo=timezone.utc), False
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc), True
    except ValueError:
        return None, False


def truth_state(value, requirement, blockers, conditions):
    if value is False:
        blockers.append(requirement)
    elif value is not True:
        conditions.append(requirement + " must be confirmed")


def annual_counts(referrals, year):
    counts = {}
    for row in referrals if isinstance(referrals, list) else []:
        if not isinstance(row, dict) or row.get("referral_status") != "COMPLETE":
            continue
        dt, _ = parse_time(row.get("date"))
        account = row.get("referred_account_type")
        if dt and dt.year == year and isinstance(account, str):
            counts[account] = counts.get(account, 0) + 1
    return counts


def rolling_events(referrer, as_of):
    values = referrer.get("successful_bonus_timestamps")
    from_dates = False
    if not isinstance(values, list):
        values = [r.get("date") for r in referrer.get("referrals", [])
                  if isinstance(r, dict) and r.get("referral_status") == "COMPLETE"]
        from_dates = True
    events, exact = [], True
    for value in values:
        dt, has_time = parse_time(value)
        if dt:
            events.append(dt)
            exact = exact and has_time
    cutoff = as_of - timedelta(days=9)
    return [dt for dt in events if cutoff <= dt <= as_of], exact and not from_dates


def tenure_days(referrer, as_of):
    opened, _ = parse_time(referrer.get("first_checking_opened"))
    if not opened or opened > as_of:
        return None
    return (as_of.date() - opened.date()).days


def option_for(program, candidate, referrer, count, tenure, eligibility_confirmed):
    blockers, conditions = [], []
    deposit = candidate.get("deposit")
    if program["qualifying_deposit"] is not None:
        if deposit is None:
            conditions.append("ability to make the required new-money deposit must be confirmed")
        elif deposit < program["qualifying_deposit"]:
            blockers.append("stated deposit is below the qualifying deposit requirement")

    if count >= program["annual_cap"]:
        blockers.append("annual referral cap has been reached")

    required_tenure = program.get("tenure_days")
    if required_tenure is not None:
        if eligibility_confirmed is not True and tenure is None:
            conditions.append("referrer checking tenure/current eligibility must be confirmed")
        elif tenure is not None and tenure < required_tenure:
            blockers.append("referrer does not meet the documented checking-tenure requirement")
    elif eligibility_confirmed is not True:
        conditions.append("referrer eligibility must be confirmed; this program's source does not state its exact tenure threshold")

    if candidate["kind"] == "personal":
        age = candidate.get("age")
        if "minimum_age" in program:
            if age is None:
                conditions.append("candidate age must be confirmed")
            elif age < program["minimum_age"] or age > program["maximum_age"]:
                blockers.append("candidate is outside the account age range")
            elif age < 18 and program.get("minor_guardian_required"):
                conditions.append("guardian requirement for a minor Light Green holder must be met")
        truth_state(candidate.get("different_address"), "candidate must be registered at a different address from the referrer", blockers, conditions)
    else:
        age = candidate.get("business_age_years")
        if "maximum_business_age_years" in program:
            if age is None:
                conditions.append("business formation age must be confirmed")
            elif age > program["maximum_business_age_years"]:
                blockers.append("business exceeds the startup formation-age requirement")
        if program.get("requires_enterprise"):
            truth_state(candidate.get("enterprise"), "business must qualify as an enterprise", blockers, conditions)
        truth_state(candidate.get("different_primary_owner"), "business primary owner must differ from every existing Rho-Bank business account", blockers, conditions)

    truth_state(candidate.get("new_customer"), "candidate must be a new Rho-Bank customer with no account (including closed) in the prior 12 months", blockers, conditions)
    truth_state(candidate.get("no_other_promotion"), "referral cannot be combined with another new-account promotion or sign-up bonus", blockers, conditions)
    truth_state(candidate.get("one_referral_code"), "only one referral code may be applied", blockers, conditions)
    truth_state(candidate.get("opening_eligibility_confirmed"), "account-opening eligibility must be confirmed", blockers, conditions)

    status = "ineligible" if blockers else ("conditional" if conditions else "eligible")
    return {
        "account": program["account"],
        "status": status,
        "referrer_bonus": program["referrer_bonus"],
        "referred_bonus": program["referred_bonus"],
        "combined_bonus": program["referrer_bonus"] + program["referred_bonus"],
        "qualifying_deposit": program["qualifying_deposit"],
        "deposit_window_days": program["deposit_window_days"],
        "annual_cap": program["annual_cap"],
        "completed_this_calendar_year": count,
        "annual_capacity_remaining": max(0, program["annual_cap"] - count),
        "blockers": blockers,
        "conditions": conditions
    }


def main():
    try:
        case = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "errors": ["stdin must contain one valid JSON object: " + str(exc)]}))
        return
    if not isinstance(case, dict):
        print(json.dumps({"status": "error", "errors": ["top-level input must be an object"]}))
        return

    errors = []
    as_of, _ = parse_time(case.get("as_of"))
    if not as_of:
        errors.append("as_of is required and must be an ISO timestamp or YYYY-MM-DD")
    referrer = case.get("referrer")
    if not isinstance(referrer, dict):
        errors.append("referrer must be an object")
        referrer = {}
    candidates = case.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        errors.append("candidates must be a nonempty array")
        candidates = []
    for i, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            errors.append("candidates[%d] must be an object" % i)
            continue
        if not isinstance(candidate.get("name"), str) or not candidate["name"].strip():
            errors.append("candidates[%d].name is required" % i)
        if candidate.get("kind") not in ("personal", "business"):
            errors.append("candidates[%d].kind must be personal or business" % i)
        if not isinstance(candidate.get("deposit"), (int, float)) or candidate["deposit"] < 0:
            errors.append("candidates[%d].deposit must be a nonnegative number" % i)
    if errors:
        print(json.dumps({"status": "error", "errors": errors}, indent=2))
        return

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    counts = annual_counts(referrer.get("referrals", []), as_of.year)
    known_tenure = tenure_days(referrer, as_of)
    confirmed = referrer.get("referral_eligibility_confirmed") is True
    gate_missing = []
    if not confirmed:
        gate_missing.append("current referrer referral eligibility must be confirmed before recommendations are communicated")
    if not confirmed and known_tenure is None:
        gate_missing.append("first checking-account opening date or an eligibility result is missing")

    recent, exact = rolling_events(referrer, as_of)
    shared = catalog["shared_terms"]
    rolling_count = len(recent)
    promotion = catalog["business_promotion"]
    start, _ = parse_time(promotion["starts"])
    end, _ = parse_time(promotion["ends"])
    promotion_active = start <= as_of <= (end + timedelta(days=1) - timedelta(microseconds=1))

    output_candidates = []
    rank_status = {"eligible": 0, "conditional": 1, "ineligible": 2}
    for candidate in candidates:
        programs = [p for p in catalog["programs"] if p["kind"] == candidate["kind"]]
        options = [option_for(p, candidate, referrer, counts.get(p["account"], 0), known_tenure, confirmed) for p in programs]
        by_account = {p["account"]: p for p in programs}
        def ranking(option):
            promo_rank = 9
            if promotion_active and candidate["kind"] == "business":
                promo_rank = by_account[option["account"]].get("promotion_priority", 9)
            return (rank_status[option["status"]], promo_rank, -option["combined_bonus"], option["account"])
        options.sort(key=ranking)
        recommendation = next((o for o in options if o["status"] == "eligible"), None)
        output_candidates.append({"name": candidate["name"], "kind": candidate["kind"], "options": options, "recommended_option": recommendation})

    result = {
        "status": "ok",
        "referrer_gate": {
            "can_discuss_recommendations": confirmed,
            "documented_tenure_days": known_tenure,
            "missing_or_unconfirmed": gate_missing
        },
        "rolling_9_day_limit": {
            "cap": shared["rolling_bonus_cap"],
            "successful_bonuses_in_current_window": rolling_count,
            "remaining_slots": max(0, shared["rolling_bonus_cap"] - rolling_count),
            "timestamp_precision": "exact" if exact else "date-level or unavailable",
            "warning": "Plan no more than two successful referral bonuses in any rolling 9-day interval."
        },
        "active_business_promotion": promotion_active,
        "candidates": output_candidates,
        "shared_conditions": {
            "qualifying_deposit_must_be_new_money": True,
            "deposit_retention_days_after_qualification_period": shared["deposit_retention_days_after_qualification_period"],
            "possible_clawback_if_referred_account_closes_within_days": shared["clawback_account_closure_days"],
            "both_accounts_must_remain_in_good_standing": True
        },
        "timing": "The shared rolling cap governs bonus receipt across all checking products; do not schedule more than two successful bonuses inside any rolling 9-day window."
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
