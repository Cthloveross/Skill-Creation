#!/usr/bin/env python3
"""Evaluate documented business checking referral programs.

Reads JSON from stdin and writes a JSON assessment to stdout.  It performs no
network, banking, or file-system actions beyond stdin/stdout.
"""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

PROGRAMS = [
    {"name": "Beige Account", "referrer_bonus": 500, "annual_cap": 15,
     "qualifying_deposit": 100000, "deposit_window_days": 120,
     "tenure_days": 120},
    {"name": "True Blue Account", "referrer_bonus": 350, "annual_cap": 15,
     "qualifying_deposit": 50000, "deposit_window_days": 120,
     "tenure_days": 90},
    {"name": "World Blue Account", "referrer_bonus": 300, "annual_cap": 12,
     "qualifying_deposit": 25000, "deposit_window_days": 90,
     "tenure_days": 90},
    {"name": "Lime Green Account", "referrer_bonus": 200, "annual_cap": 12,
     "qualifying_deposit": 15000, "deposit_window_days": 90,
     "tenure_days": 90},
    {"name": "Cobalt Blue Account", "referrer_bonus": 150, "annual_cap": 10,
     "qualifying_deposit": 7500, "deposit_window_days": 90,
     "tenure_days": 60},
    {"name": "Sky Blue Account", "referrer_bonus": 150, "annual_cap": 8,
     "qualifying_deposit": None, "deposit_window_days": None,
     "tenure_days": None},
    {"name": "Navy Blue Account", "referrer_bonus": 100, "annual_cap": 10,
     "qualifying_deposit": 5000, "deposit_window_days": 90,
     "tenure_days": 60},
]


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(field + " must be a YYYY-MM-DD string")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(field + " must use YYYY-MM-DD") from exc


def normalize_money(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("planned_new_money_deposit must be numeric") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("planned_new_money_deposit must be a nonnegative finite number")
    return amount


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    as_of = parse_date(payload.get("as_of"), "as_of")
    deposit = normalize_money(payload.get("planned_new_money_deposit"))
    referrals = payload.get("completed_referrals")
    if not isinstance(referrals, list):
        raise ValueError("completed_referrals must be an array")

    opened_raw = payload.get("earliest_checking_opened")
    opened = parse_date(opened_raw, "earliest_checking_opened") if opened_raw else None
    tenure = (as_of - opened).days if opened else None
    if tenure is not None and tenure < 0:
        raise ValueError("earliest_checking_opened cannot be after as_of")

    complete = []
    invalid_referral_dates = False
    for index, item in enumerate(referrals):
        if not isinstance(item, dict):
            raise ValueError("completed_referrals[%d] must be an object" % index)
        if item.get("referral_status") != "COMPLETE":
            continue
        try:
            referral_date = parse_date(item.get("date"), "completed_referrals[%d].date" % index)
        except ValueError:
            invalid_referral_dates = True
            continue
        complete.append((referral_date, item.get("referred_account_type")))

    # A date-only history cannot prove the exact timestamp boundary.  Count
    # records from the last eight full prior calendar days through as_of as a
    # conservative visible approximation and label it accordingly.
    rolling_start = as_of - timedelta(days=8)
    rolling_count = sum(1 for d, _ in complete if rolling_start <= d <= as_of)
    rolling_assessment = "pass" if rolling_count < 2 else "blocked"
    unknown = []
    if invalid_referral_dates:
        unknown.append("One or more COMPLETE referrals had an unusable date.")
    unknown.append("Exact timestamps are required to conclusively apply the rolling 9-day limit; this result uses supplied calendar dates.")
    if opened is None:
        unknown.append("Earliest checking-account opening date is required to confirm referrer tenure.")

    conditions = payload.get("general_conditions", {})
    if not isinstance(conditions, dict):
        raise ValueError("general_conditions must be an object")
    condition_labels = {
        "prospect_new_customer": "The referred business must be a new Rho-Bank customer with no account or account closure in the prior 12 months.",
        "different_registered_address": "The referrer and referred person must have different registered addresses.",
        "different_business_primary_owner": "The referred business must have a different primary owner from any existing Rho-Bank business account.",
        "no_other_promotion": "The referral bonus cannot be combined with another new-account or sign-up promotion.",
        "one_referral_code": "Only one referral code may be applied to the new account.",
    }
    failed_conditions = []
    for key, label in condition_labels.items():
        value = conditions.get(key)
        if value is False:
            failed_conditions.append(label)
        elif value is not True:
            unknown.append(label)

    programs = []
    for program in PROGRAMS:
        reasons = []
        eligible = True
        required_deposit = program["qualifying_deposit"]
        if required_deposit is None:
            eligible = False
            reasons.append("The documented materials do not provide sufficient qualifying-deposit and tenure terms for a safe comparison.")
        elif deposit < Decimal(required_deposit):
            eligible = False
            reasons.append("Planned new-money deposit is below the $%s qualifying deposit." % required_deposit)
        if program["tenure_days"] is None:
            eligible = False
        elif tenure is None:
            eligible = False
            reasons.append("Earliest checking opening date is needed to confirm the %d-day tenure requirement." % program["tenure_days"])
        elif tenure < program["tenure_days"]:
            eligible = False
            reasons.append("Referrer tenure is below the %d-day requirement." % program["tenure_days"])
        annual_count = sum(1 for d, account in complete if d.year == as_of.year and account == program["name"])
        if annual_count >= program["annual_cap"]:
            eligible = False
            reasons.append("The %d-per-calendar-year program cap has already been reached." % program["annual_cap"])
        if rolling_count >= 2:
            eligible = False
            reasons.append("Two COMPLETE referral bonuses appear in the supplied rolling 9-day date window.")
        if failed_conditions:
            eligible = False
            reasons.extend(failed_conditions)
        output = dict(program)
        output["annual_complete_count"] = annual_count
        output["eligible"] = eligible
        output["reasons"] = reasons
        programs.append(output)

    eligible_programs = [p for p in programs if p["eligible"]]
    recommended = max(eligible_programs, key=lambda p: p["referrer_bonus"], default=None)
    return {
        "as_of": as_of.isoformat(),
        "planned_new_money_deposit": float(deposit),
        "referrer_tenure_days": tenure,
        "rolling_complete_count": rolling_count,
        "rolling_window_basis": "%s through %s using calendar dates" % (rolling_start.isoformat(), as_of.isoformat()),
        "rolling_limit_assessment": rolling_assessment,
        "programs": programs,
        "recommended_program": recommended,
        "unknown": list(dict.fromkeys(unknown)),
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), separators=(",", ":"), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
