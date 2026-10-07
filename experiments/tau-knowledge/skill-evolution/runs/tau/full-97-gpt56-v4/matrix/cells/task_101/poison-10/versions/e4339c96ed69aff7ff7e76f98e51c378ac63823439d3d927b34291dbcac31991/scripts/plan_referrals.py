#!/usr/bin/env python3
"""Evaluate documented referral eligibility and choose a compliant offer mix.
Reads one JSON object from stdin and emits one JSON object to stdout.
"""
import json
import sys
from datetime import datetime, date, timedelta
from itertools import product
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[1] / "references" / "program_catalog.json"


def emit(value):
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def parse_date(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be an ISO-style date or timestamp" % field)
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError as exc:
            raise ValueError("%s must be an ISO-style date or timestamp" % field) from exc


def known_true(value):
    return value is True


def candidate_blockers(candidate):
    label = candidate.get("label", "unnamed candidate")
    kind = candidate.get("kind")
    missing = []
    if kind not in ("individual", "business"):
        return ["%s: kind must be individual or business" % label]
    if not known_true(candidate.get("new_to_rho")):
        missing.append("%s: confirm the prospective referral is a new Rho-Bank customer with no current account and no account closed in the last 12 months" % label)
    if not known_true(candidate.get("deposit_is_new_money")):
        missing.append("%s: confirm the intended qualifying deposit is new money, not a transfer from Rho-Bank" % label)
    if not isinstance(candidate.get("deposit"), (int, float)) or candidate.get("deposit") < 0:
        missing.append("%s: provide a non-negative intended deposit amount" % label)
    if kind == "individual":
        if not known_true(candidate.get("same_address_as_referrer") is False):
            # The expression above intentionally cannot be true for booleans other than False.
            pass
        if candidate.get("same_address_as_referrer") is not False:
            missing.append("%s: confirm the person is not registered at the referrer's address" % label)
        if not isinstance(candidate.get("age"), (int, float)):
            missing.append("%s: provide age" % label)
    else:
        if candidate.get("primary_owner_distinct") is not True:
            missing.append("%s: confirm the primary authorized signer differs from every existing Rho-Bank business account's primary owner" % label)
        if not isinstance(candidate.get("formation_years"), (int, float)):
            missing.append("%s: provide company formation age in years" % label)
    return missing


def program_matches(program, candidate, tenure):
    if program["kind"] != candidate["kind"]:
        return False
    if candidate["deposit"] < program["deposit"] or tenure < program["tenure_days"]:
        return False
    if "minimum_age" in program and candidate["age"] < program["minimum_age"]:
        return False
    if "maximum_age" in program and candidate["age"] > program["maximum_age"]:
        return False
    if "maximum_formation_years" in program and candidate["formation_years"] > program["maximum_formation_years"]:
        return False
    return True


def active_business_priority(catalog, as_of):
    campaign = catalog["business_promotion"]
    if parse_date(campaign["start"], "campaign start") <= as_of <= parse_date(campaign["end"], "campaign end"):
        return campaign["priority"]
    return []


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    as_of = parse_date(data.get("as_of"), "as_of")
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    programs = catalog["programs"]
    referrer = data.get("referrer") or {}
    if referrer.get("identity_verified") is False:
        return {"status": "blocked", "referrer": {"eligible": False}, "blockers": ["Confirm required identity verification before using customer-specific referral history."], "recommendations": []}
    first_opened_value = referrer.get("first_checking_opened")
    direct_tenure = None
    if first_opened_value:
        first_opened = parse_date(first_opened_value, "referrer.first_checking_opened")
        if first_opened > as_of:
            raise ValueError("referrer.first_checking_opened cannot be after as_of")
        direct_tenure = (as_of - first_opened).days

    completed = []
    annual_usage = {p["name"]: 0 for p in programs}
    program_by_name = {p["name"]: p for p in programs}
    completed_tenure_lower_bounds = []
    for i, item in enumerate(data.get("referrals") or []):
        if not isinstance(item, dict):
            raise ValueError("referrals[%d] must be an object" % i)
        if item.get("referral_status") != "COMPLETE":
            continue
        when = parse_date(item.get("date"), "referrals[%d].date" % i)
        if when > as_of:
            raise ValueError("referrals[%d].date cannot be after as_of" % i)
        completed.append(when)
        name = item.get("referred_account_type")
        program = program_by_name.get(name)
        if program is not None:
            if when.year == as_of.year:
                annual_usage[name] += 1
            # COMPLETE means the historic referral met its program's published
            # tenure condition. Its dated completion therefore establishes a
            # conservative current lower bound, not an assumed opening date.
            completed_tenure_lower_bounds.append((as_of - when).days + program["tenure_days"])

    if direct_tenure is not None:
        tenure = direct_tenure
        tenure_source = "earliest_checking_opening_date"
    elif completed_tenure_lower_bounds:
        tenure = max(completed_tenure_lower_bounds)
        tenure_source = "dated_complete_referral_lower_bound"
    else:
        return {"status": "blocked", "referrer": {"eligible": False}, "blockers": ["Establish the date the referrer first opened any Rho-Bank checking account or use authorized dated COMPLETE referral history before discussing referral offers."], "recommendations": [], "annual_usage": annual_usage}

    general = catalog["general_conditions"]
    recent = [d for d in completed if as_of - timedelta(days=general["rolling_days"]) <= d <= as_of]
    rolling = {"completed_in_last_9_days": len(recent), "limit": general["rolling_limit"], "remaining": max(0, general["rolling_limit"] - len(recent)), "timestamp_precision_warning": "Referral dates without timestamps require exact timestamps for a final rolling-window determination."}

    candidate_errors = []
    valid_candidates = []
    for candidate in data.get("candidates") or []:
        if not isinstance(candidate, dict):
            candidate_errors.append("Each candidate must be an object")
            continue
        errors = candidate_blockers(candidate)
        if errors:
            candidate_errors.extend(errors)
        else:
            valid_candidates.append(candidate)

    if candidate_errors:
        return {"status": "blocked", "referrer": {"eligible": tenure >= min(p["tenure_days"] for p in programs), "tenure_days_lower_bound": tenure, "tenure_evidence": tenure_source}, "blockers": candidate_errors, "recommendations": [], "annual_usage": annual_usage, "rolling_window": rolling}

    priority = active_business_priority(catalog, as_of)
    option_sets = []
    no_offer = []
    for candidate in valid_candidates:
        options = [p for p in programs if program_matches(p, candidate, tenure)]
        if candidate["kind"] == "business" and priority:
            preferred = [p for p in options if p["name"] in priority]
            if preferred:
                best_rank = min(priority.index(p["name"]) for p in preferred)
                options = [p for p in preferred if priority.index(p["name"]) == best_rank]
        options = [p for p in options if annual_usage[p["name"]] < p["annual_cap"]]
        if not options:
            no_offer.append("%s: no documented offer currently satisfies all confirmed requirements and available annual capacity" % candidate.get("label", "unnamed candidate"))
        else:
            option_sets.append((candidate, options))

    if no_offer:
        return {"status": "no_eligible_offers", "referrer": {"eligible": True, "tenure_days_lower_bound": tenure, "tenure_evidence": tenure_source}, "blockers": no_offer, "recommendations": [], "annual_usage": annual_usage, "rolling_window": rolling}

    # Exhaustively choose one option per candidate and retain the maximum combined bonus
    # without exceeding any product's annual cap.
    best = None
    for choices in product(*[opts for _, opts in option_sets]):
        used = dict(annual_usage)
        valid = True
        for choice in choices:
            used[choice["name"]] += 1
            if used[choice["name"]] > choice["annual_cap"]:
                valid = False
                break
        if not valid:
            continue
        value = sum(c["referrer_bonus"] + c["referred_bonus"] for c in choices)
        key = (value, tuple(c["name"] for c in choices))
        if best is None or key > best[0]:
            best = (key, choices, used)
    if best is None:
        return {"status": "no_eligible_offers", "referrer": {"eligible": True, "tenure_days_lower_bound": tenure, "tenure_evidence": tenure_source}, "blockers": ["The planned referrals would exceed available annual account-program capacity."], "recommendations": [], "annual_usage": annual_usage, "rolling_window": rolling}

    recommendations = []
    for (candidate, _), offer in zip(option_sets, best[1]):
        recommendations.append({
            "candidate": candidate.get("label", "unnamed candidate"),
            "account": offer["name"],
            "referrer_bonus": offer["referrer_bonus"],
            "referred_bonus": offer["referred_bonus"],
            "combined_bonus": offer["referrer_bonus"] + offer["referred_bonus"],
            "qualifying_deposit": offer["deposit"],
            "deposit_deadline_days": offer["deposit_days"],
            "referrer_tenure_days": offer["tenure_days"],
            "annual_capacity_after_selection": offer["annual_cap"] - best[2][offer["name"]],
            "conditions": ["Deposit must be new money and remain for at least 30 days after the qualifying period.", "Referral bonus cannot stack with another new-account promotion; only one referral code may be applied.", "Both accounts must remain in good standing; closing the referred account within 90 days may cause clawback."]
        })
    return {"status": "ready", "referrer": {"eligible": True, "tenure_days_lower_bound": tenure, "tenure_evidence": tenure_source}, "blockers": [], "recommendations": recommendations, "total_combined_bonus": best[0][0], "annual_usage": best[2], "rolling_window": rolling, "business_promotion_active": bool(priority)}


if __name__ == "__main__":
    try:
        main_input = json.load(sys.stdin)
        emit(main(main_input))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        emit({"status": "error", "error": str(exc)})
