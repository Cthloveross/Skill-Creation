#!/usr/bin/env python3
"""Deterministic referral-capacity and prerequisite assessment.
Reads one JSON object from stdin and writes one JSON object to stdout.
No network, filesystem, or banking actions are performed.
"""
import json
import sys
from datetime import datetime, timedelta, timezone

PRODUCTS = {
    "Gold Years": {"aliases": {"gold years", "gold years account"}, "tenure_days": 30,
                   "annual_cap": 6, "deposit": "$1,000 within 90 days", "age_min": 62},
    "Dark Green": {"aliases": {"dark green", "dark green account"}, "tenure_days": 45,
                   "annual_cap": 6, "deposit": "$1,000 within 60 days", "age_min": 17, "age_max": 26},
    "Light Green": {"aliases": {"light green", "light green account"}, "tenure_days": 14,
                    "annual_cap": None, "deposit": "$100 within 90 days", "age_min": 13, "age_max": 24},
    "Sky Blue": {"aliases": {"sky blue", "sky blue account"}, "tenure_days": 45,
                 "annual_cap": 8, "deposit": "at least $10,000 within 90 days", "company_age_max": 4},
}


def fail(message):
    print(json.dumps({"error": message}, sort_keys=True))
    raise SystemExit(2)


def parse_dt(value, field):
    if not isinstance(value, str) or not value:
        fail(field + " must be a nonempty ISO-8601 timestamp or YYYY-MM-DD date")
    date_only = len(value) == 10 and value[4:5] == "-" and value[7:8] == "-"
    try:
        if date_only:
            dt = datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
    except ValueError:
        fail(field + " is not a valid ISO-8601 date or timestamp")
    return dt, date_only


def canonical_product(value):
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    for name, rule in PRODUCTS.items():
        if normalized == name.lower() or normalized in rule["aliases"]:
            return name
    return None


def boolean_check(candidate, key, label, findings):
    value = candidate.get(key)
    if value is True:
        findings.append({"condition": label, "result": "satisfied"})
    elif value is False:
        findings.append({"condition": label, "result": "failed"})
    else:
        findings.append({"condition": label, "result": "unconfirmed"})


def main(data):
    if not isinstance(data, dict):
        fail("input must be a JSON object")
    as_of, _ = parse_dt(data.get("as_of"), "as_of")
    referrals = data.get("referrals", [])
    candidates = data.get("candidates", [])
    if not isinstance(referrals, list) or not isinstance(candidates, list):
        fail("referrals and candidates must be arrays")

    cutoff = as_of - timedelta(days=9)
    annual = {name: 0 for name in PRODUCTS}
    definite_rolling = 0
    possible_boundary = 0
    warnings = []
    for index, record in enumerate(referrals):
        if not isinstance(record, dict):
            fail("referrals[%d] must be an object" % index)
        # Parse every supplied record timestamp, including non-completed records,
        # so malformed source data is never silently ignored.
        when, date_only = parse_dt(record.get("timestamp", record.get("date")), "referrals[%d].date" % index)
        if str(record.get("status", record.get("referral_status", ""))).upper() != "COMPLETE":
            continue
        product = canonical_product(record.get("account_type", record.get("referred_account_type", record.get("product"))))
        if product and when.year == as_of.year:
            annual[product] += 1
        if when > as_of:
            continue
        if not date_only:
            if when >= cutoff:
                definite_rolling += 1
        else:
            day_end = when + timedelta(days=1) - timedelta(microseconds=1)
            if when >= cutoff:
                definite_rolling += 1
            elif day_end >= cutoff:
                possible_boundary += 1
                warnings.append("A date-only completed referral falls on the rolling-window boundary; obtain its exact timestamp.")

    referrer = data.get("referrer", {})
    if not isinstance(referrer, dict):
        fail("referrer must be an object")
    opened = referrer.get("earliest_checking_opened_at")
    opened_dt = None
    if opened is not None:
        opened_dt, _ = parse_dt(opened, "referrer.earliest_checking_opened_at")

    output_candidates = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            fail("candidates[%d] must be an object" % index)
        product = canonical_product(candidate.get("product"))
        if not product:
            fail("candidates[%d].product is unsupported" % index)
        rule = PRODUCTS[product]
        findings = []
        if referrer.get("identity_verified") is True:
            findings.append({"condition": "referrer identity and authority verified", "result": "satisfied"})
        else:
            findings.append({"condition": "referrer identity and authority verified", "result": "unconfirmed"})
        if opened_dt is None:
            findings.append({"condition": "referrer has %d-day checking tenure" % rule["tenure_days"], "result": "unconfirmed"})
        elif as_of - opened_dt >= timedelta(days=rule["tenure_days"]):
            findings.append({"condition": "referrer has %d-day checking tenure" % rule["tenure_days"], "result": "satisfied"})
        else:
            findings.append({"condition": "referrer has %d-day checking tenure" % rule["tenure_days"], "result": "failed"})

        kind = candidate.get("kind")
        if product == "Sky Blue":
            if kind not in (None, "business"):
                findings.append({"condition": "recipient is a qualifying startup/business", "result": "failed"})
            age = candidate.get("company_age_years")
            if isinstance(age, (int, float)):
                findings.append({"condition": "company is within 4 years of formation", "result": "satisfied" if age <= 4 and age >= 0 else "failed"})
            else:
                findings.append({"condition": "company is within 4 years of formation", "result": "unconfirmed"})
            boolean_check(candidate, "different_business_primary_owner", "primary authorized signer is not tied to an existing Rho-Bank business account", findings)
        else:
            if kind not in (None, "consumer"):
                findings.append({"condition": "recipient is an individual consumer", "result": "failed"})
            age = candidate.get("age")
            if isinstance(age, (int, float)):
                ok = age >= rule.get("age_min", -float("inf")) and age <= rule.get("age_max", float("inf"))
                findings.append({"condition": "recipient meets %s age requirement" % product, "result": "satisfied" if ok else "failed"})
            else:
                findings.append({"condition": "recipient meets %s age requirement" % product, "result": "unconfirmed"})

        boolean_check(candidate, "new_customer", "recipient is new to Rho-Bank with no current or prior-12-month closed account", findings)
        boolean_check(candidate, "different_registered_address", "recipient has a different registered address", findings)
        boolean_check(candidate, "other_promotion", "no other new-account promotion or sign-up bonus is applied", findings)
        # Here True for other_promotion means a failure, so correct the just-added finding.
        if candidate.get("other_promotion") is True:
            findings[-1]["result"] = "failed"
        elif candidate.get("other_promotion") is False:
            findings[-1]["result"] = "satisfied"
        else:
            findings[-1]["result"] = "unconfirmed"

        cap = rule["annual_cap"]
        used = annual[product]
        annual_result = "unconfirmed" if cap is None else ("satisfied" if used < cap else "failed")
        findings.append({"condition": "annual %s completed-referral cap" % product,
                         "result": annual_result,
                         "completed_this_year": used, "cap": cap})
        # A date-only record on the cutoff can make capacity uncertain. A definite
        # full window is a failure; a possibly full window requires exact time data.
        if definite_rolling >= 2:
            rolling_result = "failed"
        elif definite_rolling + possible_boundary >= 2:
            rolling_result = "unconfirmed"
        else:
            rolling_result = "satisfied"
        findings.append({"condition": "cross-product rolling nine-day bonus limit",
                         "result": rolling_result,
                         "definite_completed_count": definite_rolling,
                         "possible_completed_count": definite_rolling + possible_boundary,
                         "cap": 2})
        failed = any(item["result"] == "failed" for item in findings)
        unknown = any(item["result"] == "unconfirmed" for item in findings)
        output_candidates.append({
            "label": candidate.get("label", "candidate_%d" % (index + 1)),
            "product": product,
            "qualifying_deposit": rule["deposit"],
            "annual_completed_count": used,
            "annual_cap": cap,
            "findings": findings,
            "ready": not failed and not unknown,
        })

    conservative_used = definite_rolling + possible_boundary
    result = {
        "as_of": data["as_of"],
        "annual_completed_counts": annual,
        "rolling_nine_day": {
            "cap": 2,
            "definite_completed_count": definite_rolling,
            "possible_count_with_boundary_dates": conservative_used,
            "definite_remaining_capacity": max(0, 2 - definite_rolling),
            "conservative_remaining_capacity": max(0, 2 - conservative_used),
            "timestamp_precision_warnings": warnings,
        },
        "candidates": output_candidates,
        "universal_post_opening_conditions": [
            "Qualifying deposit must be new money, not transferred from another Rho-Bank account.",
            "Qualifying deposit must remain for at least 30 days after the qualifying period ends.",
            "Both accounts must remain in good standing; a closure within 90 days may cause clawback.",
            "Only one referral code and no other new-account promotion may be used."
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main(json.load(sys.stdin))
    except json.JSONDecodeError as exc:
        fail("invalid JSON input: " + str(exc))
