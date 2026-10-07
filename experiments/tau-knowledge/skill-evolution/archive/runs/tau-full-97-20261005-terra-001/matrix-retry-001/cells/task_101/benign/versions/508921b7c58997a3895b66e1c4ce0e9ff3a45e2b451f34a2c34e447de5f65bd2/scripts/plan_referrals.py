#!/usr/bin/env python3
"""Evaluate referral eligibility from supplied facts; stdin JSON -> stdout JSON."""
import json
import sys
from datetime import datetime, date, timezone
from pathlib import Path


def fail(message):
    return {"errors": [message]}


def parse_time(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(field + " must be a nonempty ISO date or timestamp")
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.combine(date.fromisoformat(text), datetime.min.time())
        except ValueError as exc:
            raise ValueError(field + " is not ISO-8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def truth(value):
    return value is True


def unknown(value):
    return value is None or value == ""


def load_catalog():
    path = Path(__file__).resolve().parents[1] / "references" / "referral_program_catalog.json"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def company_age(candidate, now):
    if candidate.get("company_age_years") is not None:
        try:
            return float(candidate["company_age_years"])
        except (TypeError, ValueError):
            return None
    if candidate.get("formation_date"):
        formed = parse_time(candidate["formation_date"], "formation_date")
        return (now.date() - formed.date()).days / 365.2425
    return None


def add_fact_check(blockers, pending, condition, unknown_label, failed_label):
    if unknown(condition):
        pending.append(unknown_label)
    elif not truth(condition):
        blockers.append(failed_label)


def evaluate_program(program, candidate, referrer, now, annual_counts):
    blockers, pending = [], []
    name = program["name"]
    if annual_counts.get(name, 0) >= program["annual_cap"]:
        blockers.append("annual_cap_reached")

    opened = referrer.get("earliest_checking_opened")
    if opened:
        tenure = (now.date() - parse_time(opened, "earliest_checking_opened").date()).days
        if tenure < program["tenure_days"]:
            blockers.append("referrer_tenure_below_%s_days" % program["tenure_days"])
    else:
        pending.append("earliest_checking_opened_needed_for_%s_day_tenure" % program["tenure_days"])

    add_fact_check(blockers, pending, candidate.get("new_customer_confirmed"),
                   "new_customer_and_12_month_history_confirmation_needed", "referred_party_not_new_customer")
    add_fact_check(blockers, pending, candidate.get("no_other_new_account_promotion"),
                   "confirmation_of_no_other_new_account_promotion_needed", "other_new_account_promotion_incompatible")

    deposit = candidate.get("available_deposit")
    if deposit is None:
        pending.append("available_deposit_confirmation_needed")
    else:
        try:
            if float(deposit) < float(program["qualifying_deposit"]):
                blockers.append("deposit_below_%s" % program["qualifying_deposit"])
        except (TypeError, ValueError):
            pending.append("available_deposit_must_be_numeric")

    if program["kind"] == "individual":
        add_fact_check(blockers, pending, candidate.get("different_address_confirmed"),
                       "different_registered_address_confirmation_needed", "same_registered_address_not_allowed")
        age = candidate.get("age")
        if age is None:
            if "min_age" in program or "max_age" in program:
                pending.append("age_confirmation_needed")
        else:
            try:
                age = float(age)
                if age < 18 and not program.get("minor_requires_guardian"):
                    blockers.append("referred_person_must_be_18_or_older")
                if "min_age" in program and age < program["min_age"]:
                    blockers.append("below_minimum_age")
                if "max_age" in program and age > program["max_age"]:
                    blockers.append("above_maximum_age")
                if age < 18 and program.get("minor_requires_guardian"):
                    add_fact_check(blockers, pending, candidate.get("guardian_confirmed"),
                                   "guardian_confirmation_needed_for_minor", "minor_guardian_required")
            except (TypeError, ValueError):
                pending.append("age_must_be_numeric")
    else:
        add_fact_check(blockers, pending, candidate.get("different_primary_owner_confirmed"),
                       "different_primary_owner_confirmation_needed", "primary_owner_matches_existing_business_account")
        if "company_max_age_years" in program:
            age = company_age(candidate, now)
            if age is None:
                pending.append("company_formation_date_or_age_needed")
            elif age > program["company_max_age_years"]:
                blockers.append("company_exceeds_%s_year_limit" % program["company_max_age_years"])
        if program.get("enterprise_required"):
            add_fact_check(blockers, pending, candidate.get("enterprise_confirmed"),
                           "enterprise_status_confirmation_needed", "enterprise_level_business_required")

    return {"account_type": name, "referrer_bonus": program["referrer_bonus"],
            "referred_bonus": program["referred_bonus"],
            "combined_bonus": program["referrer_bonus"] + program["referred_bonus"],
            "qualifying_deposit": program["qualifying_deposit"],
            "deposit_window_days": program["deposit_window_days"],
            "annual_cap": program["annual_cap"], "annual_completed": annual_counts.get(name, 0),
            "blockers": sorted(set(blockers)), "pending": sorted(set(pending))}


def main(payload):
    if not isinstance(payload, dict):
        return fail("top-level input must be an object")
    try:
        now = parse_time(payload.get("current_time"), "current_time")
    except ValueError as exc:
        return fail(str(exc))
    catalog = load_catalog()
    programs = payload.get("programs", catalog["programs"])
    if not isinstance(programs, list) or not all(isinstance(p, dict) and "name" in p and "kind" in p for p in programs):
        return fail("programs must be a list of program objects")
    referrer = payload.get("referrer")
    candidates = payload.get("candidates")
    referrals = payload.get("referrals", [])
    if not isinstance(referrer, dict) or not isinstance(candidates, list) or not isinstance(referrals, list):
        return fail("referrer, candidates, and referrals must be objects/list/list")

    errors, annual_counts, rolling = [], {}, []
    for index, referral in enumerate(referrals):
        if not isinstance(referral, dict):
            errors.append("referrals[%s] must be an object" % index)
            continue
        if str(referral.get("referral_status", "")).upper() != "COMPLETE":
            continue
        try:
            when = parse_time(referral.get("date"), "referrals[%s].date" % index)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        account = referral.get("referred_account_type")
        if not account:
            errors.append("referrals[%s] needs referred_account_type" % index)
            continue
        if when.year == now.year:
            annual_counts[account] = annual_counts.get(account, 0) + 1
        age_seconds = (now - when).total_seconds()
        if 0 <= age_seconds <= 9 * 86400:
            rolling.append({"account_type": account, "date": referral["date"]})
    if errors:
        return {"errors": errors}

    shared_blockers = []
    if referrer.get("has_active_checking") is not True:
        shared_blockers.append("active_checking_relationship_not_verified")
    if referrer.get("good_standing") is not True:
        shared_blockers.append("referrer_good_standing_not_verified")
    if not referrer.get("earliest_checking_opened"):
        shared_blockers.append("earliest_checking_opened_not_verified")
    if len(rolling) >= catalog["shared_rules"]["rolling_bonus_limit"]:
        shared_blockers.append("rolling_nine_day_bonus_limit_reached")

    active_promo = payload.get("promotion_active")
    if active_promo is None:
        promo = catalog["promotion"]
        active_promo = promo["start"] <= now.date().isoformat() <= promo["end"]
    priority = {name: i for i, name in enumerate(catalog["promotion"]["priority"])}
    results = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict) or candidate.get("kind") not in ("individual", "business"):
            return fail("each candidate needs kind individual or business")
        evaluated = [evaluate_program(p, candidate, referrer, now, annual_counts)
                     for p in programs if p.get("kind") == candidate["kind"]]
        eligible = [x for x in evaluated if not x["blockers"] and not x["pending"]]
        pending = [x for x in evaluated if not x["blockers"] and x["pending"]]
        disqualified = [x for x in evaluated if x["blockers"]]
        if candidate["kind"] == "business" and active_promo:
            eligible.sort(key=lambda x: (priority.get(x["account_type"], 999), -x["combined_bonus"], x["account_type"]))
        else:
            eligible.sort(key=lambda x: (-x["combined_bonus"], x["account_type"]))
        results.append({"candidate_id": candidate.get("id", str(index)), "kind": candidate["kind"],
                        "recommended_program": eligible[0] if eligible and not shared_blockers else None,
                        "eligible_programs": eligible, "pending_programs": pending,
                        "disqualified_programs": disqualified})

    limit = catalog["shared_rules"]["rolling_bonus_limit"]
    return {"errors": [], "eligibility_blockers": shared_blockers,
            "annual_completed_by_account": annual_counts,
            "rolling_window": {"completed_bonuses_in_window": rolling,
                               "capacity_remaining": max(0, limit - len(rolling)),
                               "limit": limit,
                               "window_days": catalog["shared_rules"]["rolling_window_days"]},
            "promotion_active": bool(active_promo), "candidates": results,
            "required_shared_conditions": catalog["shared_rules"]}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps(fail("invalid JSON input: " + str(exc))))
    except Exception as exc:
        print(json.dumps(fail("invalid input: " + str(exc))))
