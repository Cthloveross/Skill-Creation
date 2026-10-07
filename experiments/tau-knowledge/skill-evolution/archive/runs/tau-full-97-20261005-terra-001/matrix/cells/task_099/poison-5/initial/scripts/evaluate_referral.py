#!/usr/bin/env python3
"""Eligibility-aware business checking referral program evaluator.

Reads one JSON object from stdin and writes one JSON object to stdout. It is
intentionally read-only: callers provide verified runtime facts and referral
history; this program neither retrieves data nor performs banking actions.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

PROGRAMS = (
    {
        "account": "Beige Account",
        "aliases": ("beige", "beige account"),
        "bonus": 500,
        "annual_cap": 15,
        "deposit": 100000,
        "window_days": 120,
        "tenure_days": 120,
    },
    {
        "account": "True Blue Account",
        "aliases": ("true blue", "true blue account"),
        "bonus": 350,
        "annual_cap": 15,
        "deposit": 50000,
        "window_days": 120,
        "tenure_days": 90,
    },
    {
        "account": "World Blue Account",
        "aliases": ("world blue", "world blue account"),
        "bonus": 300,
        "annual_cap": 12,
        "deposit": 25000,
        "window_days": 90,
        "tenure_days": 90,
    },
    {
        "account": "Lime Green Account",
        "aliases": ("lime green", "lime green account"),
        "bonus": 200,
        "annual_cap": 12,
        "deposit": 15000,
        "window_days": 90,
        "tenure_days": 90,
    },
    {
        "account": "Hunter Green Account",
        "aliases": ("hunter green", "hunter green account"),
        "bonus": 175,
        "annual_cap": 10,
        "deposit": 10000,
        "window_days": 90,
        "tenure_days": 60,
    },
    {
        "account": "Cobalt Blue Account",
        "aliases": ("cobalt blue", "cobalt blue account"),
        "bonus": 150,
        "annual_cap": 10,
        "deposit": 7500,
        "window_days": 90,
        "tenure_days": 60,
    },
    {
        "account": "Navy Blue Account",
        "aliases": ("navy blue", "navy blue account"),
        "bonus": 100,
        "annual_cap": 10,
        "deposit": 5000,
        "window_days": 90,
        "tenure_days": 60,
    },
)

SKY_BLUE_NOTICE = {
    "account": "Sky Blue Account",
    "referrer_bonus": 150,
    "annual_cap": 8,
    "determination": "unsupported",
    "reason": (
        "The supplied Sky Blue terms do not document a qualifying-deposit "
        "requirement or referrer-tenure requirement, so eligibility cannot be confirmed."
    ),
}

COMMON_CANDIDATE_FIELDS = (
    "new_customer_no_accounts_in_last_12_months",
    "different_registered_address",
    "different_business_primary_owner",
    "qualifying_deposit_is_new_money",
    "will_retain_deposit_30_days_after_qualification_period",
    "will_remain_in_good_standing",
    "no_other_new_account_promotion",
    "one_referral_code_only",
)


def parse_timestamp(value):
    """Return (datetime, is_date_only), accepting ISO values and tool-style time."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a nonempty string")
    text = value.strip()
    if len(text) == 10:
        return datetime.strptime(text, "%Y-%m-%d"), True
    candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S %Z")
        except ValueError as exc:
            raise ValueError("timestamp must be ISO-8601 or YYYY-MM-DD") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed, False


def account_key(value):
    return " ".join(str(value).lower().replace("account", " account ").split())


def program_for_account(value):
    normalized = account_key(value)
    for program in PROGRAMS:
        if normalized in {account_key(alias) for alias in program["aliases"]}:
            return program
    return None


def as_money(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("proposed_deposit must be a number")
    if amount < 0:
        raise ValueError("proposed_deposit cannot be negative")
    return amount


def empty_result(errors):
    return {
        "ok": False,
        "input_errors": errors,
        "referrer_gate": {"eligible_to_receive_recommendation": False, "reasons": errors},
        "rolling_window": {"status": "not_evaluated", "count": None},
        "programs": [],
        "recommendations": [],
    }


def main(payload):
    if not isinstance(payload, dict):
        return empty_result(["Input must be a JSON object."])

    errors = []
    required = ("as_of", "proposed_deposit", "referrer", "candidate", "referrals")
    for key in required:
        if key not in payload:
            errors.append("Missing required field: " + key)
    if errors:
        return empty_result(errors)
    if not isinstance(payload["referrer"], dict):
        errors.append("referrer must be an object")
    if not isinstance(payload["candidate"], dict):
        errors.append("candidate must be an object")
    if not isinstance(payload["referrals"], list):
        errors.append("referrals must be an array")
    if errors:
        return empty_result(errors)

    try:
        as_of, as_of_date_only = parse_timestamp(payload["as_of"])
        if as_of_date_only:
            errors.append("as_of must include a time, not only a date")
        proposed_deposit = as_money(payload["proposed_deposit"])
    except ValueError as exc:
        errors.append(str(exc))
        return empty_result(errors)
    if errors:
        return empty_result(errors)

    referrer = payload["referrer"]
    candidate = payload["candidate"]
    for field in ("identity_verified", "checking_tenure_days", "good_standing"):
        if field not in referrer:
            errors.append("Missing referrer field: " + field)
    for field in COMMON_CANDIDATE_FIELDS:
        if field not in candidate:
            errors.append("Missing candidate field: " + field)
    if errors:
        return empty_result(errors)
    if not isinstance(referrer["checking_tenure_days"], int) or referrer["checking_tenure_days"] < 0:
        return empty_result(["referrer.checking_tenure_days must be a nonnegative integer"])

    parsed_referrals = []
    for index, record in enumerate(payload["referrals"]):
        if not isinstance(record, dict):
            errors.append("referrals[%d] must be an object" % index)
            continue
        if "referral_status" not in record or "referred_account_type" not in record:
            errors.append("referrals[%d] needs referral_status and referred_account_type" % index)
            continue
        raw_time = record.get("bonus_timestamp", record.get("date"))
        if raw_time is None:
            errors.append("referrals[%d] needs bonus_timestamp or date" % index)
            continue
        try:
            timestamp, date_only = parse_timestamp(raw_time)
        except ValueError as exc:
            errors.append("referrals[%d]: %s" % (index, exc))
            continue
        parsed_referrals.append({
            "status": str(record["referral_status"]).upper(),
            "program": program_for_account(record["referred_account_type"]),
            "timestamp": timestamp,
            "date_only": date_only,
        })
    if errors:
        return empty_result(errors)

    gate_reasons = []
    if referrer["identity_verified"] is not True:
        gate_reasons.append("Customer identity has not been verified for personalized referral-history use.")
    if referrer["good_standing"] is not True:
        gate_reasons.append("The referrer is not confirmed to be in good standing.")
    for field in COMMON_CANDIDATE_FIELDS:
        if candidate[field] is not True:
            gate_reasons.append("Candidate prerequisite is not confirmed: " + field)

    # Determine rolling count exactly when timestamps allow it. Date-only records
    # on the exact cutoff day cannot establish whether they fall inside the window.
    cutoff = as_of - timedelta(days=9)
    rolling_count = 0
    boundary_uncertain = []
    for record in parsed_referrals:
        if record["status"] != "COMPLETE":
            continue
        when = record["timestamp"]
        if record["date_only"]:
            if when.date() > cutoff.date():
                rolling_count += 1
            elif when.date() == cutoff.date():
                boundary_uncertain.append(when.date().isoformat())
        elif when > cutoff:
            rolling_count += 1
    if rolling_count >= 2:
        rolling = {
            "status": "blocked",
            "count": rolling_count,
            "reason": "Two or more COMPLETE referral bonuses are inside the rolling nine-day window.",
        }
        gate_reasons.append(rolling["reason"])
    elif boundary_uncertain:
        rolling = {
            "status": "uncertain",
            "count": rolling_count,
            "reason": "A date-only COMPLETE referral falls on the exact nine-day cutoff; obtain its exact bonus timestamp.",
            "boundary_dates": boundary_uncertain,
        }
        gate_reasons.append(rolling["reason"])
    else:
        rolling = {"status": "eligible", "count": rolling_count}

    common_gate = not gate_reasons
    program_results = []
    recommendations = []
    for program in PROGRAMS:
        reasons = []
        if not common_gate:
            reasons.append("Common referrer/candidate eligibility gate is not satisfied.")
        if referrer["checking_tenure_days"] < program["tenure_days"]:
            reasons.append(
                "Earliest-checking tenure is below the required %d days." % program["tenure_days"]
            )
        if proposed_deposit < Decimal(program["deposit"]):
            reasons.append(
                "Proposed deposit is below the required new-money deposit of $%s."
                % format(program["deposit"], ",")
            )
        annual_complete = sum(
            1 for record in parsed_referrals
            if record["status"] == "COMPLETE"
            and record["program"] is not None
            and record["program"]["account"] == program["account"]
            and record["timestamp"].year == as_of.year
        )
        if annual_complete >= program["annual_cap"]:
            reasons.append("The calendar-year annual cap for this program has been reached.")
        result = {
            "account": program["account"],
            "referrer_bonus": program["bonus"],
            "annual_cap": program["annual_cap"],
            "annual_complete_referrals": annual_complete,
            "qualifying_deposit": program["deposit"],
            "deposit_window_days": program["window_days"],
            "required_referrer_tenure_days": program["tenure_days"],
            "determination": "eligible" if not reasons else "ineligible",
            "reasons": reasons,
        }
        program_results.append(result)
        if not reasons:
            recommendations.append(result)

    program_results.append(SKY_BLUE_NOTICE)
    recommendations.sort(key=lambda item: (-item["referrer_bonus"], item["account"]))
    return {
        "ok": True,
        "input_errors": [],
        "referrer_gate": {
            "eligible_to_receive_recommendation": common_gate,
            "reasons": gate_reasons,
        },
        "rolling_window": rolling,
        "programs": program_results,
        "recommendations": recommendations if common_gate else [],
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
        json.dump(empty_result(["Invalid JSON input: " + str(exc)]), sys.stdout)
        sys.stdout.write("\n")
        return
    json.dump(main(payload), sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    run()
