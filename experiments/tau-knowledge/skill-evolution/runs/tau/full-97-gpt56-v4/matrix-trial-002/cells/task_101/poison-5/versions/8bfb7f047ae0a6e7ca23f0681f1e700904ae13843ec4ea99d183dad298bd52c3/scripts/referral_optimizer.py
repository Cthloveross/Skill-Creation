#!/usr/bin/env python3
"""Fail-closed referral program eligibility and ranking helper.

Input: JSON described in SKILL.md. Output: JSON with either
{"status":"needs_confirmation", "blockers":[...]} or
{"status":"ok", "recommendations":[...], "rolling_window":{...}}.
No banking operation is performed.
"""
import json
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation

PROGRAMS = [
    {"account": "Blue", "group": "personal", "referrer_bonus": 35, "referred_bonus": 30, "cap": 5, "deposit": 500, "deadline_days": 60, "tenure_days": 30},
    {"account": "Light Green", "group": "personal", "referrer_bonus": 15, "referred_bonus": 25, "cap": 3, "deposit": 100, "deadline_days": 90, "tenure_days": 14, "age_min": 13, "age_max": 24},
    {"account": "Dark Green", "group": "personal", "referrer_bonus": 40, "referred_bonus": 30, "cap": 6, "deposit": 1000, "deadline_days": 60, "tenure_days": 45},
    {"account": "Gold Years", "group": "personal", "referrer_bonus": 50, "referred_bonus": 75, "cap": 6, "deposit": 1000, "deadline_days": 90, "tenure_days": 30, "age_min": 62},
    {"account": "Green Fee-Free", "group": "personal", "referrer_bonus": 20, "referred_bonus": 35, "cap": 4, "deposit": 300, "deadline_days": 60, "tenure_days": 30},
    {"account": "Evergreen", "group": "personal", "referrer_bonus": 35, "referred_bonus": 25, "cap": 6, "deposit": 750, "deadline_days": 60, "tenure_days": 45},
    {"account": "Bluest", "group": "personal", "referrer_bonus": 75, "referred_bonus": 50, "cap": 8, "deposit": 2000, "deadline_days": 90, "tenure_days": 60},
    {"account": "Sky Blue", "group": "business", "referrer_bonus": 150, "referred_bonus": 250, "cap": 8, "deposit": 10000, "deadline_days": 90, "tenure_days": 45, "startup_max_age": 4},
    {"account": "Cobalt Blue", "group": "business", "referrer_bonus": 150, "referred_bonus": 100, "cap": 10, "deposit": 7500, "deadline_days": 90, "tenure_days": 60},
    {"account": "Navy Blue", "group": "business", "referrer_bonus": 100, "referred_bonus": 75, "cap": 10, "deposit": 5000, "deadline_days": 90, "tenure_days": 60},
    {"account": "Lime Green", "group": "business", "referrer_bonus": 200, "referred_bonus": 150, "cap": 12, "deposit": 15000, "deadline_days": 90, "tenure_days": 90},
    {"account": "True Blue", "group": "business", "referrer_bonus": 350, "referred_bonus": 250, "cap": 15, "deposit": 50000, "deadline_days": 120, "tenure_days": 90},
    {"account": "World Blue", "group": "business", "referrer_bonus": 300, "referred_bonus": 200, "cap": 12, "deposit": 25000, "deadline_days": 90, "tenure_days": 90},
    {"account": "Beige", "group": "business", "referrer_bonus": 500, "referred_bonus": 350, "cap": 15, "deposit": 100000, "deadline_days": 120, "tenure_days": 120, "enterprise_only": True},
]

COMMON_CANDIDATE_CONFIRMATIONS = (
    "new_customer_confirmed", "different_address_confirmed",
    "deposit_new_money_confirmed", "deposit_retention_confirmed",
    "no_promotion_stacking_confirmed",
)

def parse_datetime(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a YYYY-MM-DD string")
    return date.fromisoformat(value)

def money(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("deposit_amount must be numeric")

def years_tenure(opened, today):
    return (today - opened).days

def blockers_for_referrer(referrer, today):
    blockers = []
    if referrer.get("identity_verified") is not True:
        blockers.append("Referrer identity is not verified (two profile factors and verification log are required).")
    if referrer.get("good_standing") is not True:
        blockers.append("Referrer checking account good standing is unconfirmed.")
    try:
        opened = parse_date(referrer.get("earliest_checking_open_date"))
        if opened > today:
            blockers.append("Earliest checking opening date cannot be in the future.")
    except ValueError:
        blockers.append("Referrer's earliest checking opening date is missing or invalid.")
    if not isinstance(referrer.get("annual_complete_counts"), dict):
        blockers.append("Current-calendar-year COMPLETE referral counts by account are missing.")
    return blockers

def blockers_for_candidate(candidate):
    name = str(candidate.get("name") or "Unnamed prospect")
    result = []
    kind = candidate.get("kind")
    if kind not in ("individual", "business", "startup", "enterprise"):
        result.append(f"{name}: kind must be individual, business, startup, or enterprise.")
    for field in COMMON_CANDIDATE_CONFIRMATIONS:
        if candidate.get(field) is not True:
            label = field.replace("_", " ")
            result.append(f"{name}: {label} is not confirmed.")
    if kind in ("business", "startup", "enterprise") and candidate.get("different_primary_owner_confirmed") is not True:
        result.append(f"{name}: different primary authorized signer/owner is not confirmed.")
    try:
        if money(candidate.get("deposit_amount")) < 0:
            result.append(f"{name}: deposit amount cannot be negative.")
    except ValueError:
        result.append(f"{name}: qualifying deposit amount is missing or invalid.")
    if kind == "individual":
        age = candidate.get("age")
        if not isinstance(age, (int, float)):
            result.append(f"{name}: age is missing or invalid.")
        elif age < 18 and candidate.get("guardian_confirmed") is not True:
            result.append(f"{name}: a guardian is required for an under-18 Light Green prospect.")
    if kind == "startup" and not isinstance(candidate.get("formation_age_years"), (int, float)):
        result.append(f"{name}: formation age is required to assess Sky Blue.")
    return result

def product_matches(program, candidate, tenure, counts):
    kind = candidate["kind"]
    if program["group"] == "personal" and kind != "individual":
        return None
    if program["group"] == "business" and kind == "individual":
        return None
    if program.get("enterprise_only") and kind != "enterprise":
        return None
    if program.get("startup_max_age") is not None:
        # Sky Blue is a startup product; generic businesses cannot be presumed eligible.
        if kind != "startup" or candidate.get("formation_age_years") > program["startup_max_age"]:
            return None
    if tenure < program["tenure_days"]:
        return None
    if money(candidate["deposit_amount"]) < Decimal(program["deposit"]):
        return None
    if counts.get(program["account"], 0) >= program["cap"]:
        return None
    age = candidate.get("age")
    if program.get("age_min") is not None and (not isinstance(age, (int, float)) or age < program["age_min"]):
        return None
    if program.get("age_max") is not None and (not isinstance(age, (int, float)) or age > program["age_max"]):
        return None
    return {
        "account": program["account"],
        "referrer_bonus": program["referrer_bonus"],
        "referred_bonus": program["referred_bonus"],
        "combined_bonus": program["referrer_bonus"] + program["referred_bonus"],
        "annual_cap": program["cap"],
        "remaining_annual_capacity": program["cap"] - counts.get(program["account"], 0),
        "qualifying_deposit": program["deposit"],
        "deposit_deadline_days": program["deadline_days"],
        "required_tenure_days": program["tenure_days"],
    }

def rolling_window(now, stamps):
    parsed = []
    for stamp in stamps:
        try:
            parsed.append(parse_datetime(stamp))
        except ValueError:
            raise ValueError("recent_successful_bonus_timestamps contains an invalid timestamp")
    active = sorted(t for t in parsed if now - timedelta(days=9) <= t <= now)
    result = {"active_successful_bonus_count": len(active), "may_receive_bonus_now": len(active) < 2}
    if len(active) >= 2:
        # Use a conservative instant after the ninth-day anniversary.
        result["earliest_safe_next_bonus_time"] = (active[0] + timedelta(days=9, seconds=1)).isoformat()
        result["warning"] = "A third successful referral bonus in the rolling nine-day window will be automatically denied."
    else:
        result["warning"] = "Track bonus qualification timestamps; applications alone do not guarantee rolling-window availability."
    return result

def main(payload):
    try:
        now = parse_datetime(payload.get("now"))
    except ValueError as exc:
        return {"status": "needs_confirmation", "blockers": [f"Invalid now value: {exc}"]}
    referrer = payload.get("referrer")
    candidates = payload.get("candidates")
    if not isinstance(referrer, dict) or not isinstance(candidates, list) or not candidates:
        return {"status": "needs_confirmation", "blockers": ["A referrer object and at least one candidate are required."]}
    blockers = blockers_for_referrer(referrer, now.date())
    for candidate in candidates:
        if not isinstance(candidate, dict):
            blockers.append("Each candidate must be an object.")
        else:
            blockers.extend(blockers_for_candidate(candidate))
    if blockers:
        return {"status": "needs_confirmation", "blockers": blockers}
    opened = parse_date(referrer["earliest_checking_open_date"])
    tenure = years_tenure(opened, now.date())
    counts = referrer["annual_complete_counts"]
    if any(not isinstance(v, int) or v < 0 for v in counts.values()):
        return {"status": "needs_confirmation", "blockers": ["Annual COMPLETE counts must be nonnegative integers."]}
    try:
        rolling = rolling_window(now, payload.get("recent_successful_bonus_timestamps", []))
    except ValueError as exc:
        return {"status": "needs_confirmation", "blockers": [str(exc)]}
    recommendations = []
    for candidate in candidates:
        options = [p for program in PROGRAMS if (p := product_matches(program, candidate, tenure, counts))]
        options.sort(key=lambda item: (-item["combined_bonus"], -item["referrer_bonus"], item["account"]))
        recommendations.append({
            "candidate": candidate.get("name"),
            "referrer_tenure_days": tenure,
            "eligible_options_ranked": options,
            "best_option": options[0] if options else None,
            "note": None if options else "No program meets the confirmed category, tenure, deposit, and annual-cap constraints."
        })
    return {
        "status": "ok",
        "recommendations": recommendations,
        "rolling_window": rolling,
        "conditions": [
            "All shown options remain contingent on successful qualification, both accounts remaining in good standing, and no promotion stacking.",
            "Qualifying new money must remain in the account at least 30 days after the qualifying period ends.",
            "Closing the referred account within 90 days may result in a referral-bonus clawback."
        ]
    }

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"status": "needs_confirmation", "blockers": [f"Invalid optimizer input: {exc}"]}, sort_keys=True))
