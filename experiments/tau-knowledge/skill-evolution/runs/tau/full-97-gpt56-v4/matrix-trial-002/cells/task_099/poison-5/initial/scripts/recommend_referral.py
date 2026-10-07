#!/usr/bin/env python3
"""Rank referral offers from JSON stdin without performing banking actions.

Input and output are documented in SKILL.md. All product terms and customer data
are supplied at runtime; this helper deliberately contains no product-specific terms.
"""
import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation


def fail(message):
    print(json.dumps({"error": message}, sort_keys=True))
    raise SystemExit(2)


def parse_timestamp(value, field):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a nonempty ISO-8601 timestamp")
    # A bare date is useful for calendar-year counts but cannot prove exact rolling limits.
    if len(value) == 10:
        return datetime.fromisoformat(value), True
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone or be a bare date")
    return parsed, False


def money(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be numeric")
    if result < 0:
        raise ValueError(f"{field} must be nonnegative")
    return result


def same_zone(value, as_of):
    # Convert aware values to the reference timezone before comparing date/year.
    if value.tzinfo is not None and as_of.tzinfo is not None:
        return value.astimezone(as_of.tzinfo)
    return value


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be an object")
    as_of, as_of_is_date = parse_timestamp(data.get("as_of"), "as_of")
    if as_of_is_date:
        raise ValueError("as_of must include an exact time and timezone")
    planned = money(data.get("planned_deposit"), "planned_deposit")
    tenure = data.get("referrer_tenure_days")
    if not isinstance(tenure, int) or tenure < 0:
        raise ValueError("referrer_tenure_days must be a nonnegative integer")
    base = data.get("base_eligibility")
    if not isinstance(base, dict):
        raise ValueError("base_eligibility must be an object")
    required_base = ["new_customer", "different_address", "different_primary_owner", "age_eligible", "new_money_confirmed", "no_conflicting_promotion", "good_standing_confirmed"]
    missing_base = [k for k in required_base if base.get(k) is not True]

    referrals = data.get("referrals", [])
    offers = data.get("offers", [])
    if not isinstance(referrals, list) or not isinstance(offers, list):
        raise ValueError("offers and referrals must be arrays")

    completed = []
    for index, referral in enumerate(referrals):
        if not isinstance(referral, dict):
            raise ValueError(f"referrals[{index}] must be an object")
        if referral.get("status") != "COMPLETE":
            continue
        dt, date_only = parse_timestamp(referral.get("date"), f"referrals[{index}].date")
        completed.append((same_zone(dt, as_of), date_only, referral.get("referred_account_type", "")))

    cutoff = as_of - timedelta(days=9)
    definite_recent = 0
    uncertain_recent = False
    for dt, date_only, _ in completed:
        if date_only:
            # A date can be definitively outside only if its entire day predates cutoff.
            if dt.date() >= cutoff.date():
                uncertain_recent = True
        elif cutoff <= dt <= as_of:
            definite_recent += 1
    if definite_recent >= 2:
        rolling = {"status": "blocked", "complete_count": definite_recent, "reason": "Two or more COMPLETE referrals fall within the rolling nine-day window."}
    elif uncertain_recent:
        rolling = {"status": "unknown", "complete_count": definite_recent, "reason": "Exact referral timestamps are required to determine the rolling nine-day limit."}
    else:
        rolling = {"status": "eligible", "complete_count": definite_recent, "reason": None}

    rendered = []
    for index, offer in enumerate(offers):
        if not isinstance(offer, dict):
            raise ValueError(f"offers[{index}] must be an object")
        name = offer.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"offers[{index}].name must be nonempty")
        bonus = money(offer.get("referrer_bonus"), f"offers[{index}].referrer_bonus")
        deposit = money(offer.get("qualifying_deposit"), f"offers[{index}].qualifying_deposit")
        window = offer.get("deposit_window_days")
        min_tenure = offer.get("tenure_days")
        cap = offer.get("annual_cap")
        if not all(isinstance(x, int) and x >= 0 for x in (window, min_tenure, cap)):
            raise ValueError(f"offers[{index}] day counts and annual_cap must be nonnegative integers")
        scope = offer.get("annual_cap_scope", "program")
        if scope not in ("program", "global"):
            raise ValueError(f"offers[{index}].annual_cap_scope must be program or global")
        keys = offer.get("program_keys", [name])
        if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
            raise ValueError(f"offers[{index}].program_keys must be an array of strings")
        keys = set(keys)
        annual_count = sum(1 for dt, _, product in completed if dt.year == as_of.year and (scope == "global" or product in keys))
        blockers = []
        if missing_base:
            blockers.append("Unconfirmed or failed base eligibility: " + ", ".join(missing_base))
        if deposit > planned:
            blockers.append("Planned deposit is below the qualifying-deposit requirement.")
        if tenure < min_tenure:
            blockers.append("Referrer tenure is below the program requirement.")
        if cap == 0 or annual_count >= cap:
            blockers.append("The applicable calendar-year referral cap has been reached.")
        if rolling["status"] != "eligible":
            blockers.append(rolling["reason"])
        rendered.append({
            "name": name,
            "referrer_bonus": float(bonus),
            "qualifying_deposit": float(deposit),
            "deposit_window_days": window,
            "tenure_days": min_tenure,
            "annual_cap": cap,
            "annual_cap_scope": scope,
            "annual_complete_count": annual_count,
            "eligible": not blockers,
            "blockers": blockers,
        })

    eligible = [offer for offer in rendered if offer["eligible"]]
    recommendation = None
    if eligible:
        recommendation = sorted(eligible, key=lambda x: (-x["referrer_bonus"], x["name"].casefold()))[0]
    return {
        "base_eligibility": {"eligible": not missing_base, "missing_or_failed": missing_base},
        "rolling_window": rolling,
        "offers": rendered,
        "recommendation": recommendation,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        print(json.dumps(main(raw), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        fail(str(exc))
