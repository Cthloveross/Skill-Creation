#!/usr/bin/env python3
"""Deterministic referral preflight and recommendation evaluator.

Reads a JSON request from stdin. Writes JSON only to stdout. It performs no
network access and no banking action.
"""
import json
import sys
from datetime import date, datetime, timedelta

PROGRAMS = [
    {"account": "Light Green Account", "kind": "individual", "referrer_bonus": 15, "customer_bonus": 25, "annual_cap": 3, "deposit": 100, "deposit_days": 90, "tenure_days": 14, "min_age": 13, "max_age": 24},
    {"account": "Green Fee-Free Account", "kind": "individual", "referrer_bonus": 20, "customer_bonus": 35, "annual_cap": 4, "deposit": 300, "deposit_days": 60, "tenure_days": 30},
    {"account": "Light Blue Account", "kind": "individual", "referrer_bonus": 30, "customer_bonus": 20, "annual_cap": 5, "deposit": 500, "deposit_days": 60, "tenure_days": 30},
    {"account": "Blue Account", "kind": "individual", "referrer_bonus": 35, "customer_bonus": 30, "annual_cap": 5, "deposit": 500, "deposit_days": 60, "tenure_days": 30},
    {"account": "Dark Green Account", "kind": "individual", "referrer_bonus": 40, "customer_bonus": 30, "annual_cap": 6, "deposit": 1000, "deposit_days": 60, "tenure_days": 45, "min_age": 17, "max_age": 26},
    {"account": "Gold Years Account", "kind": "individual", "referrer_bonus": 50, "customer_bonus": 75, "annual_cap": 6, "deposit": 1000, "deposit_days": 90, "tenure_days": 30, "min_age": 62},
    {"account": "Sky Blue Account", "kind": "business", "referrer_bonus": 150, "customer_bonus": 250, "annual_cap": 8, "deposit": 10000, "deposit_days": 90, "tenure_days": 45, "startup_only": True, "max_formation_age": 4, "priority": 1},
    {"account": "Lime Green Account", "kind": "business", "referrer_bonus": 200, "customer_bonus": 150, "annual_cap": 12, "deposit": 15000, "deposit_days": 90, "tenure_days": 90, "priority": 2},
    {"account": "Navy Blue Account", "kind": "business", "referrer_bonus": 100, "customer_bonus": 75, "annual_cap": 10, "deposit": 5000, "deposit_days": 90, "tenure_days": 60},
    {"account": "Hunter Green Account", "kind": "business", "referrer_bonus": 175, "customer_bonus": 125, "annual_cap": 10, "deposit": 10000, "deposit_days": 90, "tenure_days": 60},
]


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing date")
    value = value.strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date(), ("T" in value or " " in value)
    except ValueError:
        return date.fromisoformat(value[:10]), False


def yes(value):
    return value is True


def annual_completed(referrals, account, year):
    total = 0
    for item in referrals:
        if item.get("referred_account_type") != account or item.get("referral_status") != "COMPLETE":
            continue
        try:
            when, _ = parse_date(item.get("timestamp", item.get("date")))
            if when.year == year:
                total += 1
        except ValueError:
            pass
    return total


def rolling_info(referrals, today):
    completed = []
    exact_needed = False
    for item in referrals:
        if item.get("referral_status") != "COMPLETE":
            continue
        raw = item.get("timestamp", item.get("date"))
        try:
            when, exact = parse_date(raw)
        except ValueError:
            continue
        # A date at least nine calendar days earlier might still be within the
        # exact rolling window; preserve that uncertainty for an operator.
        if (today - when).days <= 9:
            completed.append(when.isoformat())
            if not exact:
                exact_needed = True
    return {
        "completed_bonus_records_in_previous_9_days": len(completed),
        "cross_product_cap": 2,
        "can_receive_another_bonus_now": len(completed) < 2,
        "exact_timestamps_required": exact_needed,
        "relevant_record_dates": sorted(completed),
        "note": "The statutory/program limit uses exact bonus timestamps; date-only records require timestamp confirmation."
    }


def candidate_missing(candidate):
    missing = []
    if not yes(candidate.get("new_customer_confirmed")):
        missing.append("confirmation that the prospective customer has had no Rho-Bank checking, savings, or closed account in the preceding 12 months")
    if not yes(candidate.get("different_address_confirmed")):
        missing.append("confirmation that the prospective customer is not registered at the referrer’s address")
    if not yes(candidate.get("deposit_new_money_confirmed")):
        missing.append("confirmation that the qualifying deposit is new money and not a transfer from another Rho-Bank account")
    if candidate.get("kind") == "business" and not yes(candidate.get("primary_owner_different_confirmed")):
        missing.append("confirmation that the business primary authorized signer is not the primary owner of an existing Rho-Bank business account")
    return missing


def program_fits(program, candidate, tenure, referrals, year):
    if program["kind"] != candidate.get("kind"):
        return None
    if not isinstance(candidate.get("deposit_amount"), (int, float)) or candidate["deposit_amount"] < program["deposit"]:
        return None
    if tenure < program["tenure_days"]:
        return None
    used = annual_completed(referrals, program["account"], year)
    if used >= program["annual_cap"]:
        return None
    age = candidate.get("age")
    if "min_age" in program and (not isinstance(age, (int, float)) or age < program["min_age"]):
        return None
    if "max_age" in program and (not isinstance(age, (int, float)) or age > program["max_age"]):
        return None
    if program.get("startup_only") and candidate.get("is_startup") is not True:
        return None
    if "max_formation_age" in program:
        formation_age = candidate.get("formation_age_years")
        if not isinstance(formation_age, (int, float)) or formation_age > program["max_formation_age"]:
            return None
    return {
        "account": program["account"],
        "combined_bonus": program["referrer_bonus"] + program["customer_bonus"],
        "referrer_bonus": program["referrer_bonus"],
        "customer_bonus": program["customer_bonus"],
        "qualifying_deposit": program["deposit"],
        "deposit_deadline_days": program["deposit_days"],
        "referrer_tenure_days": program["tenure_days"],
        "annual_cap": program["annual_cap"],
        "completed_bonuses_this_year": used,
        "annual_slots_remaining": program["annual_cap"] - used,
        "promotion_priority": program.get("priority")
    }


def main(payload):
    errors = []
    try:
        today, _ = parse_date(payload.get("now"))
    except ValueError:
        errors.append("now must be a valid YYYY-MM-DD or ISO-8601 timestamp")
        today = None
    referrer = payload.get("referrer") if isinstance(payload.get("referrer"), dict) else {}
    opened = None
    if today:
        try:
            opened, _ = parse_date(referrer.get("earliest_checking_opened"))
            if opened > today:
                errors.append("earliest_checking_opened cannot be in the future")
        except ValueError:
            errors.append("referrer.earliest_checking_opened is required to verify tenure")
    referrals = payload.get("referrals", [])
    candidates = payload.get("candidates", [])
    if not isinstance(referrals, list):
        errors.append("referrals must be an array")
        referrals = []
    if not isinstance(candidates, list):
        errors.append("candidates must be an array")
        candidates = []

    output = {"input_errors": errors, "eligibility_gate": {}, "candidates": []}
    if errors:
        output["eligibility_gate"] = {"can_provide_recommendations": False, "blockers": errors}
        return output

    tenure = (today - opened).days
    output["rolling_window"] = rolling_info(referrals, today)
    output["eligibility_gate"] = {
        "can_provide_recommendations": True,
        "blockers": [],
        "referrer_tenure_days": tenure,
        "tenure_basis": "earliest Rho-Bank checking-account opening date"
    }
    promotion_active = date(2025, 11, 1) <= today <= date(2025, 11, 30)

    for candidate in candidates:
        if not isinstance(candidate, dict):
            output["candidates"].append({"status": "INVALID", "missing_confirmations": ["candidate must be an object"], "options": []})
            continue
        missing = candidate_missing(candidate)
        result = {"name": candidate.get("name", "Prospective referral"), "kind": candidate.get("kind"), "missing_confirmations": missing}
        if candidate.get("kind") not in ("individual", "business"):
            result.update({"status": "INVALID", "missing_confirmations": missing + ["kind must be individual or business"], "options": []})
        elif missing:
            result.update({"status": "PENDING_ELIGIBILITY", "options": []})
        else:
            options = [program_fits(p, candidate, tenure, referrals, today.year) for p in PROGRAMS]
            options = [o for o in options if o]
            if promotion_active and candidate.get("kind") == "business":
                prioritized = [o for o in options if o.get("promotion_priority") in (1, 2)]
                if prioritized:
                    options = sorted(prioritized, key=lambda o: o["promotion_priority"])
                else:
                    options = sorted(options, key=lambda o: o["combined_bonus"], reverse=True)
            else:
                options = sorted(options, key=lambda o: o["combined_bonus"], reverse=True)
            result.update({"status": "ELIGIBLE" if options else "NO_QUALIFYING_ACCOUNT", "options": options})
        output["candidates"].append(result)
    return output


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(request), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"input_errors": [str(exc)], "eligibility_gate": {"can_provide_recommendations": False, "blockers": ["invalid evaluator input"]}, "candidates": []}, sort_keys=True))
        sys.exit(1)
