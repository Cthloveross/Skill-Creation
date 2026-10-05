#!/usr/bin/env python3
"""Evaluate eligibility and optimize referral choices from JSON stdin."""
import json
import sys
from datetime import datetime, timedelta, timezone
from itertools import product
from referral_catalog import PROGRAMS


def parse_time(value):
    if not value or not isinstance(value, str):
        return None
    try:
        text = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return None
        return parsed
    except ValueError:
        return None


def day_age(start, end):
    return (end - start).total_seconds() / 86400


def current_year_completions(records, now):
    counts = {}
    parsed_complete = []
    date_only = False
    for record in records:
        if record.get("status") != "COMPLETE":
            continue
        timestamp = parse_time(record.get("timestamp"))
        if timestamp is None:
            date_only = True
            continue
        if timestamp.year == now.year:
            account = record.get("account_type")
            counts[account] = counts.get(account, 0) + 1
        parsed_complete.append(timestamp)
    return counts, parsed_complete, date_only


def rolling_count(timestamps, at_time):
    # Conservative inclusive boundary: an event exactly nine days earlier remains relevant.
    start = at_time - timedelta(days=9)
    return sum(1 for stamp in timestamps if start <= stamp <= at_time)


def option_for(candidate, program, capacity, tenure_days):
    blockers = []
    unresolved = []
    if capacity.get(program["account_type"], 0) <= 0:
        blockers.append("annual_cap_reached")
    if tenure_days is None:
        unresolved.append("earliest_checking_opening_date")
    elif tenure_days < program["tenure_days"]:
        blockers.append("referrer_tenure_below_threshold")
    deposit = candidate.get("planned_deposit")
    if not isinstance(deposit, (int, float)):
        unresolved.append("planned_deposit")
    elif deposit < program["deposit"]:
        blockers.append("deposit_below_product_requirement")
    if candidate.get("new_customer_confirmed") is not True:
        (unresolved if candidate.get("new_customer_confirmed") is None else blockers).append("new_customer_status")
    if candidate["kind"] == "individual":
        if candidate.get("different_address_confirmed") is not True:
            (unresolved if candidate.get("different_address_confirmed") is None else blockers).append("different_registered_address")
        age = candidate.get("age")
        if "age_min" in program:
            if not isinstance(age, (int, float)):
                unresolved.append("age")
            elif age < program["age_min"] or age > program.get("age_max", float("inf")):
                blockers.append("product_age_ineligible")
    else:
        if candidate.get("business_owner_different_confirmed") is not True:
            (unresolved if candidate.get("business_owner_different_confirmed") is None else blockers).append("different_primary_business_owner")
        if "startup_max_formation_years" in program:
            formation = candidate.get("startup_formation_years")
            if not isinstance(formation, (int, float)):
                unresolved.append("startup_formation_age")
            elif formation > program["startup_max_formation_years"]:
                blockers.append("startup_formation_age_ineligible")
    return {
        "account_type": program["account_type"],
        "combined_bonus": program["referrer_bonus"] + program["referred_bonus"],
        "referrer_bonus": program["referrer_bonus"],
        "referred_bonus": program["referred_bonus"],
        "qualifying_deposit": program["deposit"],
        "deposit_window_days": program["deposit_days"],
        "referrer_tenure_days": program["tenure_days"],
        "blockers": blockers,
        "unresolved": unresolved,
        "feasible": not blockers and not unresolved,
        "promo_rank": program.get("promo_rank"),
    }


def choose(options_by_candidate, capacities, enforce_priority):
    """Brute-force small referral sets; capacity applies per account product."""
    choices = []
    for options in options_by_candidate:
        choices.append([None] + [item for item in options if item["feasible"]])
    best = None
    for assignment in product(*choices):
        used = {}
        for item in assignment:
            if item:
                used[item["account_type"]] = used.get(item["account_type"], 0) + 1
        if any(used[name] > capacities.get(name, 0) for name in used):
            continue
        # Promotional ordering is a tie-breaker among equal total value, never a constraint.
        score = sum(item["combined_bonus"] for item in assignment if item)
        priority = sum((3 - item["promo_rank"]) for item in assignment if item and item.get("promo_rank")) if enforce_priority else 0
        key = (score, priority, sum(item is not None for item in assignment))
        if best is None or key > best[0]:
            best = (key, assignment)
    return best[1] if best else tuple(None for _ in options_by_candidate)


def main(payload):
    now = parse_time(payload.get("as_of"))
    if now is None:
        return {"error": "as_of must be an ISO-8601 timestamp with timezone"}
    referrer = payload.get("referrer") or {}
    records = referrer.get("complete_referrals") or []
    counts, timestamps, date_only = current_year_completions(records, now)
    planned = parse_time(payload.get("planned_referral_time")) or now
    first_opened = parse_time(referrer.get("first_checking_opened"))
    tenure = day_age(first_opened, now) if first_opened else None
    capacity = {p["account_type"]: max(0, p["annual_cap"] - counts.get(p["account_type"], 0)) for p in PROGRAMS}
    missing = []
    if referrer.get("identity_verified") is not True:
        missing.append("verified_customer_identity")
    if first_opened is None:
        missing.append("earliest_checking_opening_date")
    if date_only:
        missing.append("exact_complete_referral_timestamps")
    recent = rolling_count(timestamps, planned)
    if recent >= 2:
        missing.append("rolling_nine_day_capacity")
    gate = {"passed": not missing, "unresolved_or_failed": missing, "tenure_days": tenure, "completed_in_planned_window": recent}
    result = {"referrer_gate": gate, "data_gaps": list(missing), "warnings": [], "candidates": [], "recommendations": [], "combined_bonus_total": 0, "requires_manual_confirmation": bool(missing)}
    if date_only:
        result["warnings"].append("Date-only COMPLETE history cannot resolve an exact rolling nine-day boundary.")
    if recent >= 2:
        result["warnings"].append("The planned time already has two COMPLETE bonuses in its prior rolling nine-day interval; do not submit another until capacity returns.")
    candidates = payload.get("candidates") or []
    if not gate["passed"]:
        return result
    by_candidate = []
    for candidate in candidates:
        kind = candidate.get("kind")
        if kind not in ("individual", "business"):
            result["candidates"].append({"name": candidate.get("name"), "blockers": ["invalid_candidate_kind"], "options": []})
            by_candidate.append([])
            continue
        options = [option_for(candidate, p, capacity, tenure) for p in PROGRAMS if p["kind"] == kind]
        result["candidates"].append({"name": candidate.get("name"), "blockers": [], "options": options})
        by_candidate.append(options)
    if any(item.get("blockers") for item in result["candidates"]):
        result["requires_manual_confirmation"] = True
        return result
    # Do not select while a candidate has unresolved eligibility; this prevents conditional recommendations.
    if any(any(option["unresolved"] for option in item["options"]) for item in result["candidates"]):
        result["data_gaps"].append("candidate_eligibility_facts")
        result["requires_manual_confirmation"] = True
        return result
    selected = choose(by_candidate, capacity, bool(payload.get("apply_november_2025_business_priority")))
    for candidate, item in zip(candidates, selected):
        if item is None:
            result["warnings"].append("No feasible program remains for " + str(candidate.get("name", "an unnamed candidate")) + ".")
            continue
        clean = {key: value for key, value in item.items() if key not in ("blockers", "unresolved", "feasible", "promo_rank")}
        result["recommendations"].append({"candidate": candidate.get("name"), **clean})
        result["combined_bonus_total"] += item["combined_bonus"]
    return result

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), indent=2, sort_keys=True))
    except (json.JSONDecodeError, TypeError) as exc:
        print(json.dumps({"error": "invalid input JSON", "detail": str(exc)}))
        sys.exit(1)
