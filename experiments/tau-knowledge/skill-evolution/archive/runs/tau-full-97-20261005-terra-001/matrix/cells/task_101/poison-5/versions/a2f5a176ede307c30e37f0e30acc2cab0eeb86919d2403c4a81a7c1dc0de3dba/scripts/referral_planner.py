#!/usr/bin/env python3
"""JSON stdin/stdout referral recommendation planner; Python standard library only."""
import json
import sys
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

CATALOG = json.loads((Path(__file__).resolve().parent.parent / "references" / "referral_programs.json").read_text(encoding="utf-8"))


def parse_datetime(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        if "T" in normalized:
            result = datetime.fromisoformat(normalized)
        else:
            result = datetime.combine(date.fromisoformat(normalized), datetime.min.time())
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except ValueError:
        return None


def parse_date(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def truth(value):
    return value is True


def formation_age(recipient, today):
    if isinstance(recipient.get("formation_age_years"), (int, float)):
        return float(recipient["formation_age_years"])
    formed = parse_date(recipient.get("formation_date"))
    return None if formed is None else (today - formed).days / 365.2425


def referrer_blockers(referrer, as_of):
    blockers = []
    if not truth(referrer.get("identity_verified")):
        blockers.append("Referrer identity has not been verified and logged.")
    if not truth(referrer.get("checking_good_standing_confirmed")):
        blockers.append("An eligible referrer checking relationship in good standing has not been confirmed.")
    opened = parse_date(referrer.get("first_checking_opened"))
    if opened is None:
        blockers.append("Earliest Rho-Bank checking opening date is missing or invalid.")
        tenure = None
    else:
        tenure = (as_of.date() - opened).days
        if tenure < 0:
            blockers.append("Earliest checking opening date is in the future.")
    return blockers, tenure


def annual_counts(referrals, year):
    counts = {}
    for item in referrals:
        when = parse_datetime(item.get("date"))
        if item.get("referral_status") == "COMPLETE" and when and when.year == year:
            product = item.get("referred_account_type")
            counts[product] = counts.get(product, 0) + 1
    return counts


def rolling(referrals, as_of):
    start = as_of - timedelta(days=CATALOG["general_rules"]["rolling_window_days"])
    completed = []
    undated = 0
    for item in referrals:
        if item.get("referral_status") != "COMPLETE":
            continue
        when = parse_datetime(item.get("date"))
        if when is None:
            undated += 1
        elif start <= when <= as_of:
            completed.append({"date": when.isoformat(), "referred_account_type": item.get("referred_account_type")})
    return completed, undated


def recipient_conditions(recipient, program, tenure, today):
    conditions, hard_failures = [], []
    required = CATALOG["general_rules"]["required_confirmations"]
    for field in required:
        if not truth(recipient.get(field)):
            conditions.append(field)
    if program["kind"] == "business" and not truth(recipient.get("different_primary_owner_confirmed")):
        conditions.append("different_primary_owner_confirmed")

    amount = recipient.get("deposit_amount")
    if not isinstance(amount, (int, float)):
        conditions.append("deposit_amount")
    elif amount < program["deposit_required"]:
        hard_failures.append("Deposit amount is below the documented qualifying deposit.")

    if program["kind"] == "personal":
        age = recipient.get("age")
        if not isinstance(age, (int, float)):
            conditions.append("age")
        else:
            minimum = program.get("minimum_age", CATALOG["general_rules"]["personal_default_minimum_age"])
            if age < minimum:
                hard_failures.append("Recipient does not meet the documented minimum age.")
            if "maximum_age" in program and age > program["maximum_age"]:
                hard_failures.append("Recipient exceeds this account's documented age range.")
            if age < 18 and program.get("minor_guardian_exception") and not truth(recipient.get("guardian_confirmed")):
                conditions.append("guardian_confirmed")
    else:
        age_years = formation_age(recipient, today)
        if "maximum_formation_age_years" in program:
            if age_years is None:
                conditions.append("formation_date_or_age")
            elif age_years > program["maximum_formation_age_years"]:
                hard_failures.append("Business exceeds this program's documented formation-age limit.")
    return sorted(set(conditions)), hard_failures


def promotion_active(as_of):
    promo = CATALOG["business_promotion"]
    return parse_date(promo["start"]) <= as_of.date() <= parse_date(promo["end"])


def candidate(recipient, program, tenure, counts, today, active_promo):
    conditions, failures = recipient_conditions(recipient, program, tenure, today)
    used = counts.get(program["name"], 0)
    if used >= program["annual_cap"]:
        failures.append("Annual referral-bonus cap has already been reached for this program.")
    if tenure is None:
        conditions.append("first_checking_opened")
    elif tenure < program["tenure_days"]:
        failures.append("Referrer has not met this program's tenure requirement.")
    item = {
        "program": program["name"],
        "referrer_bonus": program["referrer_bonus"],
        "referred_bonus": program["referred_bonus"],
        "combined_bonus": program["referrer_bonus"] + program["referred_bonus"],
        "qualifying_deposit": program["deposit_required"],
        "deposit_deadline_days": program["deposit_days"],
        "referrer_tenure_days": program["tenure_days"],
        "annual_cap": program["annual_cap"],
        "completed_this_calendar_year": used,
        "conditions": sorted(set(conditions)),
        "failures": failures,
        "fully_confirmed": not conditions and not failures
    }
    # Active business promotion mandates priority among otherwise fully qualified choices.
    priority = 99
    if active_promo and program["kind"] == "business":
        order = CATALOG["business_promotion"]["priority"]
        if program["name"] in order:
            priority = order.index(program["name"])
    item["promotion_rank"] = priority if active_promo and program["kind"] == "business" else None
    return item


def main(payload):
    as_of = parse_datetime(payload.get("as_of"))
    if as_of is None:
        return {"status": "invalid_input", "error": "as_of must be an ISO-8601 date or timestamp."}
    referrer = payload.get("referrer") if isinstance(payload.get("referrer"), dict) else {}
    blockers, tenure = referrer_blockers(referrer, as_of)
    referrals = payload.get("existing_referrals") if isinstance(payload.get("existing_referrals"), list) else []
    counts = annual_counts(referrals, as_of.year)
    recent, undated = rolling(referrals, as_of)
    rolling_limit = CATALOG["general_rules"]["rolling_bonus_limit"]
    base = {
        "status": "referrer_not_ready" if blockers else "ready_for_recipient_assessment",
        "referrer_blockers": blockers,
        "referrer_tenure_days": tenure,
        "rolling_window": {
            "successful_bonuses_in_prior_nine_days": len(recent),
            "capacity_before_another_successful_bonus": max(0, rolling_limit - len(recent)),
            "limit": rolling_limit,
            "undated_complete_records_not_used": undated,
            "warning": "Qualification/bonus timestamps must be monitored; referral creation dates do not guarantee rolling-window capacity."
        },
        "recipients": []
    }
    # Do not expose or rank terms before participation eligibility is established.
    if blockers:
        base["validation"] = {"passed": True, "checks": ["No program terms or recommendations emitted while referrer eligibility is unresolved."]}
        return base

    active = promotion_active(as_of)
    programs = CATALOG["programs"]
    recipients = payload.get("recipients") if isinstance(payload.get("recipients"), list) else []
    for recipient in recipients:
        if not isinstance(recipient, dict):
            base["recipients"].append({"label": None, "recommendation": None, "error": "Recipient must be an object."})
            continue
        kind = recipient.get("kind")
        items = [candidate(recipient, p, tenure, counts, as_of.date(), active) for p in programs if p["kind"] == kind]
        viable = [x for x in items if not x["failures"]]
        # Promotional order applies before dollar optimization to business programs during the stated period.
        if active and kind == "business":
            viable.sort(key=lambda x: (x["promotion_rank"] if x["promotion_rank"] is not None else 99, -x["combined_bonus"], x["program"]))
        else:
            viable.sort(key=lambda x: (-x["combined_bonus"], x["program"]))
        confirmed = [x for x in viable if x["fully_confirmed"]]
        base["recipients"].append({
            "label": recipient.get("label"),
            "recommendation": confirmed[0] if confirmed else None,
            "candidates": viable,
            "blocked_programs": [x for x in items if x["failures"]],
            "promotion_active": active if kind == "business" else False
        })
    base["validation"] = {
        "passed": all(r.get("recommendation") is None or r["recommendation"]["fully_confirmed"] for r in base["recipients"]),
        "checks": [
            "Only COMPLETE referrals were counted toward annual and rolling limits.",
            "Annual caps were counted by account type in the as_of calendar year.",
            "Recommendations require confirmed general and program-specific conditions.",
            "Business promotion priority is date-bounded."
        ]
    }
    return base


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("Top-level JSON must be an object.")
        print(json.dumps(main(incoming), sort_keys=True, separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"status": "invalid_input", "error": str(exc)}, separators=(",", ":")))
