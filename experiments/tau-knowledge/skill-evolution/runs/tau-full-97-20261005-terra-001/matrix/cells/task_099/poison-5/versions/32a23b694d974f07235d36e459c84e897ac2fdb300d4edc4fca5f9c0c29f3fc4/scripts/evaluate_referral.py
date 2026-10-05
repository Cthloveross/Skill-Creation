#!/usr/bin/env python3
"""Read-only business-checking referral comparison evaluator.

Reads one JSON object from stdin and writes one JSON object to stdout. It makes
no banking calls and does not submit or modify a referral.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

PROGRAMS = (
    {"account": "Beige Account", "aliases": ("beige", "beige account"), "bonus": 500, "annual_cap": 15, "deposit": 100000, "window_days": 120, "tenure_days": 120},
    {"account": "True Blue Account", "aliases": ("true blue", "true blue account"), "bonus": 350, "annual_cap": 15, "deposit": 50000, "window_days": 120, "tenure_days": 90},
    {"account": "World Blue Account", "aliases": ("world blue", "world blue account"), "bonus": 300, "annual_cap": 12, "deposit": 25000, "window_days": 90, "tenure_days": 90},
    {"account": "Lime Green Account", "aliases": ("lime green", "lime green account"), "bonus": 200, "annual_cap": 12, "deposit": 15000, "window_days": 90, "tenure_days": 90},
    {"account": "Hunter Green Account", "aliases": ("hunter green", "hunter green account"), "bonus": 175, "annual_cap": 10, "deposit": 10000, "window_days": 90, "tenure_days": 60},
    {"account": "Cobalt Blue Account", "aliases": ("cobalt blue", "cobalt blue account"), "bonus": 150, "annual_cap": 10, "deposit": 7500, "window_days": 90, "tenure_days": 60},
    {"account": "Navy Blue Account", "aliases": ("navy blue", "navy blue account"), "bonus": 100, "annual_cap": 10, "deposit": 5000, "window_days": 90, "tenure_days": 60},
)

CANDIDATE_FIELDS = (
    "new_customer_no_accounts_in_last_12_months",
    "different_registered_address",
    "different_business_primary_owner",
    "qualifying_deposit_is_new_money",
    "will_retain_deposit_30_days_after_qualification_period",
    "will_remain_in_good_standing",
    "no_other_new_account_promotion",
    "one_referral_code_only",
)


def empty_result(errors):
    return {
        "ok": False,
        "input_errors": errors,
        "referrer_gate": {"eligible_to_receive_recommendation": False, "reasons": errors},
        "rolling_window": {"status": "not_evaluated", "count": None},
        "programs": [],
        "recommendations": [],
        "conditional_recommendations": [],
    }


def parse_time(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a nonempty string")
    text = value.strip()
    if len(text) == 10:
        return datetime.strptime(text, "%Y-%m-%d"), True
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be ISO-8601 or YYYY-MM-DD") from exc
    if parsed.tzinfo is None:
        raise ValueError("a timestamp with time must include an offset")
    return parsed.astimezone(timezone.utc).replace(tzinfo=None), False


def parse_money(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("proposed_deposit must be numeric") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("proposed_deposit must be a nonnegative finite number")
    return amount


def normalized(value):
    return " ".join(str(value).lower().split())


def program_for(value):
    name = normalized(value)
    for program in PROGRAMS:
        if name in {normalized(alias) for alias in program["aliases"]}:
            return program
    return None


def program_record(program, annual_complete, reasons, determination):
    return {
        "account": program["account"],
        "referrer_bonus": program["bonus"],
        "annual_cap": program["annual_cap"],
        "annual_complete_referrals": annual_complete,
        "qualifying_deposit": program["deposit"],
        "deposit_window_days": program["window_days"],
        "required_referrer_tenure_days": program["tenure_days"],
        "determination": determination,
        "reasons": reasons,
    }


def evaluate(payload):
    if not isinstance(payload, dict):
        return empty_result(["Input must be a JSON object."])

    required = ("as_of", "proposed_deposit", "proposed_deposit_confirmed", "referrer", "referrals")
    errors = ["Missing required field: " + field for field in required if field not in payload]
    mode = payload.get("comparison_mode", "confirmed")
    if mode not in ("confirmed", "conditional"):
        errors.append("comparison_mode must be confirmed or conditional")
    if not isinstance(payload.get("referrer"), dict):
        errors.append("referrer must be an object")
    if not isinstance(payload.get("referrals"), list):
        errors.append("referrals must be an array")
    candidate = payload.get("candidate", {})
    if not isinstance(candidate, dict):
        errors.append("candidate must be an object when supplied")
    if errors:
        return empty_result(errors)

    try:
        as_of, as_of_date_only = parse_time(payload["as_of"])
        deposit = parse_money(payload["proposed_deposit"])
    except ValueError as exc:
        return empty_result([str(exc)])
    if as_of_date_only:
        return empty_result(["as_of must include a time and offset"])

    referrer = payload["referrer"]
    for field in ("identity_verified", "checking_tenure_days", "good_standing"):
        if field not in referrer:
            errors.append("Missing referrer field: " + field)
    if mode == "confirmed":
        for field in CANDIDATE_FIELDS:
            if field not in candidate:
                errors.append("Missing candidate field: " + field)
    if errors:
        return empty_result(errors)
    tenure = referrer["checking_tenure_days"]
    if not isinstance(tenure, int) or isinstance(tenure, bool) or tenure < 0:
        return empty_result(["referrer.checking_tenure_days must be a nonnegative integer"])

    referrals = []
    for index, record in enumerate(payload["referrals"]):
        if not isinstance(record, dict):
            errors.append("referrals[%d] must be an object" % index)
            continue
        if "referral_status" not in record or "referred_account_type" not in record:
            errors.append("referrals[%d] needs referral_status and referred_account_type" % index)
            continue
        timestamp_value = record.get("bonus_timestamp", record.get("date"))
        if timestamp_value is None:
            errors.append("referrals[%d] needs bonus_timestamp or date" % index)
            continue
        try:
            stamp, date_only = parse_time(timestamp_value)
        except ValueError as exc:
            errors.append("referrals[%d]: %s" % (index, exc))
            continue
        referrals.append({
            "status": str(record["referral_status"]).upper(),
            "program": program_for(record["referred_account_type"]),
            "timestamp": stamp,
            "date_only": date_only,
        })
    if errors:
        return empty_result(errors)

    gate_reasons = []
    if referrer["identity_verified"] is not True:
        gate_reasons.append("Customer identity has not been verified for personalized referral-history use.")
    if referrer["good_standing"] is not True:
        gate_reasons.append("The referrer is not confirmed to be in good standing.")
    if mode == "confirmed":
        if payload["proposed_deposit_confirmed"] is not True:
            gate_reasons.append("The proposed qualifying new-money deposit is not confirmed as a definite amount.")
        for field in CANDIDATE_FIELDS:
            if candidate[field] is not True:
                gate_reasons.append("Candidate prerequisite is not confirmed: " + field)

    cutoff = as_of - timedelta(days=9)
    rolling_count = 0
    uncertain_boundary_dates = []
    for record in referrals:
        if record["status"] != "COMPLETE":
            continue
        if record["date_only"]:
            if record["timestamp"].date() > cutoff.date():
                rolling_count += 1
            elif record["timestamp"].date() == cutoff.date():
                uncertain_boundary_dates.append(record["timestamp"].date().isoformat())
        elif record["timestamp"] >= cutoff:
            rolling_count += 1
    if rolling_count >= 2:
        rolling = {"status": "blocked", "count": rolling_count, "reason": "Two or more COMPLETE referral bonuses are inside the rolling nine-day window."}
        gate_reasons.append(rolling["reason"])
    elif uncertain_boundary_dates:
        rolling = {"status": "uncertain", "count": rolling_count, "reason": "A date-only COMPLETE referral falls on the nine-day cutoff; obtain its exact bonus timestamp.", "boundary_dates": uncertain_boundary_dates}
        gate_reasons.append(rolling["reason"])
    else:
        rolling = {"status": "eligible", "count": rolling_count}

    common_gate = not gate_reasons
    programs = []
    confirmed = []
    conditional = []
    for program in PROGRAMS:
        annual_complete = sum(
            1 for record in referrals
            if record["status"] == "COMPLETE" and record["program"] is not None
            and record["program"]["account"] == program["account"]
            and record["timestamp"].year == as_of.year
        )
        reasons = []
        if mode == "confirmed" and not common_gate:
            reasons.append("Common referrer/candidate eligibility gate is not satisfied.")
        if tenure < program["tenure_days"]:
            reasons.append("Earliest-checking tenure is below the required %d days." % program["tenure_days"])
        if deposit < Decimal(program["deposit"]):
            reasons.append("Proposed deposit is below the required new-money deposit of $%s." % format(program["deposit"], ","))
        if annual_complete >= program["annual_cap"]:
            reasons.append("The calendar-year annual cap for this program has been reached.")
        determination = "eligible" if mode == "confirmed" and not reasons else "ineligible"
        if mode == "conditional":
            determination = "fits_planned_amount_conditionally" if not reasons else "does_not_fit_planned_amount"
        result = program_record(program, annual_complete, reasons, determination)
        programs.append(result)
        if mode == "confirmed" and determination == "eligible":
            confirmed.append(result)
        if mode == "conditional" and determination == "fits_planned_amount_conditionally":
            conditional.append(result)

    programs.append({
        "account": "Sky Blue Account", "referrer_bonus": 150, "annual_cap": 8,
        "determination": "unsupported",
        "reason": "Supplied Sky Blue terms lack a qualifying-deposit and referrer-tenure requirement, so eligibility cannot be confirmed.",
    })
    confirmed.sort(key=lambda item: (-item["referrer_bonus"], item["account"]))
    conditional.sort(key=lambda item: (-item["referrer_bonus"], item["account"]))
    return {
        "ok": True,
        "comparison_mode": mode,
        "input_errors": [],
        "referrer_gate": {"eligible_to_receive_recommendation": common_gate, "reasons": gate_reasons},
        "rolling_window": rolling,
        "programs": programs,
        "recommendations": confirmed if common_gate else [],
        "conditional_recommendations": conditional if mode == "conditional" else [],
        "common_conditions": [
            "The qualifying deposit must be new money, not a transfer from another Rho-Bank account.",
            "The qualifying deposit must remain for at least 30 days after the qualification period ends.",
            "Both accounts must remain in good standing for bonus payment.",
            "Only one referral code and no other new-account promotion may be used.",
        ],
    }


def run():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        json.dump(empty_result(["Invalid JSON input: " + str(exc)]), sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
        return
    json.dump(evaluate(payload), sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    run()
