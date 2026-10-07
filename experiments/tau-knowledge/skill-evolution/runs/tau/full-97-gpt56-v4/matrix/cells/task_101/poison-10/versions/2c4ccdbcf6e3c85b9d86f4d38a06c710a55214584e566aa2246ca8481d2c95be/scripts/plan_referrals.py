#!/usr/bin/env python3
"""Plan documented checking-account referrals without submitting any referral.

Read one JSON object from stdin and emit one JSON object to stdout.  The program
is deliberately conservative: a prospective referral with an unknown mandatory
eligibility fact is reported as blocked and is never assigned an offer.
"""
import json
import sys
from datetime import date, datetime, timedelta
from itertools import product
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[1] / "references" / "program_catalog.json"


def emit(value):
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def parse_date(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be an ISO-style date or timestamp")
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO-style date or timestamp") from exc


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def candidate_blockers(candidate):
    """Return all missing or disqualifying facts, without guessing any of them."""
    label = candidate.get("label", "unnamed candidate")
    kind = candidate.get("kind")
    blocked = []
    if kind not in ("individual", "business"):
        return [f"{label}: kind must be individual or business"]
    if candidate.get("new_to_rho") is not True:
        blocked.append(f"{label}: confirm the prospective referral is a new Rho-Bank customer with no current account and no account closed in the last 12 months")
    if candidate.get("deposit_is_new_money") is not True:
        blocked.append(f"{label}: confirm the intended qualifying deposit is new money, not a transfer from Rho-Bank")
    if not number(candidate.get("deposit")) or candidate["deposit"] < 0:
        blocked.append(f"{label}: provide a non-negative intended deposit amount")
    if kind == "individual":
        if candidate.get("same_address_as_referrer") is not False:
            blocked.append(f"{label}: confirm the person is not registered at the referrer's address")
        if not number(candidate.get("age")) or candidate["age"] < 0:
            blocked.append(f"{label}: provide age")
    else:
        if candidate.get("primary_owner_distinct") is not True:
            blocked.append(f"{label}: confirm the primary authorized signer differs from every existing Rho-Bank business account's primary owner")
        if not number(candidate.get("formation_years")) or candidate["formation_years"] < 0:
            blocked.append(f"{label}: provide company formation age in years")
    return blocked


def program_matches(program, candidate, tenure_days):
    if program["kind"] != candidate["kind"]:
        return False
    if candidate["deposit"] < program["deposit"] or tenure_days < program["tenure_days"]:
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


def read_completed(items, programs, as_of):
    """Parse dated completed history for annual and rolling-window checks."""
    by_name = {p["name"]: p for p in programs}
    annual_usage = {p["name"]: 0 for p in programs}
    completed = []
    for index, item in enumerate(items or []):
        if not isinstance(item, dict):
            raise ValueError(f"referrals[{index}] must be an object")
        if item.get("referral_status") != "COMPLETE":
            continue
        when = parse_date(item.get("date"), f"referrals[{index}].date")
        if when > as_of:
            raise ValueError(f"referrals[{index}].date cannot be after as_of")
        name = item.get("referred_account_type")
        completed.append(when)
        if name in by_name and when.year == as_of.year:
            annual_usage[name] += 1
    return completed, annual_usage


def establish_tenure(referrer, as_of):
    opened_value = referrer.get("first_checking_opened")
    if not opened_value:
        return None
    opened = parse_date(opened_value, "referrer.first_checking_opened")
    if opened > as_of:
        raise ValueError("referrer.first_checking_opened cannot be after as_of")
    return (as_of - opened).days

def option_sets_for_candidates(candidates, programs, usage, tenure, priority):
    option_sets, no_offer = [], []
    for candidate in candidates:
        options = [p for p in programs if program_matches(p, candidate, tenure)]
        # Campaign priority is a mandatory tie-breaker among qualifying business
        # products, not a reason to recommend an ineligible product.
        if candidate["kind"] == "business" and priority:
            promoted = [p for p in options if p["name"] in priority]
            if promoted:
                top_rank = min(priority.index(p["name"]) for p in promoted)
                options = [p for p in promoted if priority.index(p["name"]) == top_rank]
        options = [p for p in options if usage[p["name"]] < p["annual_cap"]]
        if not options:
            no_offer.append(f"{candidate.get('label', 'unnamed candidate')}: no documented offer currently satisfies all confirmed requirements and available annual capacity")
        else:
            option_sets.append((candidate, options))
    return option_sets, no_offer


def choose_maximum(option_sets, annual_usage):
    if not option_sets:
        return (), dict(annual_usage)
    best = None
    for choices in product(*[options for _, options in option_sets]):
        usage = dict(annual_usage)
        for offer in choices:
            usage[offer["name"]] += 1
        if any(usage[offer["name"]] > offer["annual_cap"] for offer in choices):
            continue
        value = sum(offer["referrer_bonus"] + offer["referred_bonus"] for offer in choices)
        # Stable product-name tie-break makes JSON output deterministic.
        key = (value, tuple(offer["name"] for offer in choices))
        if best is None or key > best[0]:
            best = (key, choices, usage)
    if best is None:
        return None, dict(annual_usage)
    return best[1], best[2]


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    as_of = parse_date(data.get("as_of"), "as_of")
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    programs = catalog["programs"]
    referrer = data.get("referrer") or {}
    if referrer.get("identity_verified") is not True:
        return {"status": "blocked", "referrer": {"eligible": False}, "blockers": ["Confirm required identity verification before using customer-specific referral history."], "recommendations": []}
    # This planner only evaluates authorized, read-only facts. It does not
    # submit a referral or treat its output as authorization to do so.
    completed, annual_usage = read_completed(data.get("referrals"), programs, as_of)
    tenure = establish_tenure(referrer, as_of)
    if tenure is None:
        return {"status": "blocked", "referrer": {"eligible": False}, "blockers": ["Establish the date the referrer first opened any Rho-Bank checking account before discussing referral offers."], "recommendations": [], "annual_usage": annual_usage}

    general = catalog["general_conditions"]
    recent = [when for when in completed if as_of - timedelta(days=general["rolling_days"]) <= when <= as_of]
    rolling = {
        "completed_in_last_9_days": len(recent),
        "limit": general["rolling_limit"],
        "remaining": max(0, general["rolling_limit"] - len(recent)),
        "timestamp_precision_warning": "Referral dates without timestamps require exact timestamps for a final rolling-window determination. Plan no more than two successful bonuses in any rolling nine-day interval."
    }
    referrer_info = {"eligible": tenure >= min(p["tenure_days"] for p in programs), "tenure_days": tenure}

    candidates = data.get("candidates") or []
    if not isinstance(candidates, list) or not candidates:
        return {"status": "blocked", "referrer": referrer_info, "blockers": ["Provide at least one prospective referral."], "recommendations": [], "annual_usage": annual_usage, "rolling_window": rolling}

    candidate_blocker_list, usable = [], []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            candidate_blocker_list.append("Each candidate must be an object")
            continue
        blockers = candidate_blockers(candidate)
        if blockers:
            candidate_blocker_list.extend(blockers)
        else:
            usable.append(candidate)

    priority = active_business_priority(catalog, as_of)
    option_sets, no_offer = option_sets_for_candidates(usable, programs, annual_usage, tenure, priority)
    choices, final_usage = choose_maximum(option_sets, annual_usage)
    if choices is None:
        no_offer.append("The planned referrals would exceed available annual account-program capacity.")
        choices = ()

    recommendations = []
    for (candidate, _), offer in zip(option_sets, choices):
        recommendations.append({
            "candidate": candidate.get("label", "unnamed candidate"),
            "account": offer["name"],
            "referrer_bonus": offer["referrer_bonus"],
            "referred_bonus": offer["referred_bonus"],
            "combined_bonus": offer["referrer_bonus"] + offer["referred_bonus"],
            "qualifying_deposit": offer["deposit"],
            "deposit_deadline_days": offer["deposit_days"],
            "referrer_tenure_days": offer["tenure_days"],
            "annual_capacity_after_selection": offer["annual_cap"] - final_usage[offer["name"]],
            "conditions": ["Deposit must be new money and remain for at least 30 days after the qualifying period.", "Referral bonus cannot stack with another new-account promotion; only one referral code may be applied.", "Both accounts must remain in good standing; closing the referred account within 90 days may cause clawback."]
        })

    blockers = candidate_blocker_list + no_offer
    if blockers and recommendations:
        status = "partial"
    elif blockers:
        status = "blocked" if candidate_blocker_list else "no_eligible_offers"
    else:
        status = "ready"
    return {
        "status": status,
        "referrer": referrer_info,
        "blockers": blockers,
        "recommendations": recommendations,
        "total_combined_bonus": sum(item["combined_bonus"] for item in recommendations),
        "annual_usage": final_usage,
        "rolling_window": rolling,
        "business_promotion_active": bool(priority)
    }


if __name__ == "__main__":
    try:
        main_input = json.load(sys.stdin)
        emit(main(main_input))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        emit({"status": "error", "error": str(exc)})
