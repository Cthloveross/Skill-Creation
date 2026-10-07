#!/usr/bin/env python3
"""Assess business-checking referral programs from JSON stdin without bank actions."""

import json
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

PRODUCTS = (
    {"name": "Sky Blue", "bonus": 150, "deposit": 10000, "window_days": 90, "tenure_days": 45, "annual_limit": 8},
    {"name": "Cobalt Blue", "bonus": 150, "deposit": 7500, "window_days": 90, "tenure_days": 60, "annual_limit": 10},
    {"name": "Navy Blue", "bonus": 100, "deposit": 5000, "window_days": 90, "tenure_days": 60, "annual_limit": 10},
    {"name": "Hunter Green", "bonus": 175, "deposit": 10000, "window_days": 90, "tenure_days": 60, "annual_limit": 10},
    {"name": "Lime Green", "bonus": 200, "deposit": 15000, "window_days": 90, "tenure_days": 90, "annual_limit": 12},
    {"name": "World Blue", "bonus": 300, "deposit": 25000, "window_days": 90, "tenure_days": 90, "annual_limit": 12},
    {"name": "True Blue", "bonus": 350, "deposit": 50000, "window_days": 120, "tenure_days": 90, "annual_limit": 15},
    {"name": "Beige Account", "bonus": 500, "deposit": 100000, "window_days": 120, "tenure_days": 120, "annual_limit": 15},
)

CONDITION_LABELS = {
    "referred_new_customer": "referred party is a new Rho-Bank customer with no existing checking or savings account and no account closed in the past 12 months",
    "referred_at_least_18": "referred business applicant is at least 18 years old",
    "different_address": "referrer and referred party have different registered addresses",
    "different_primary_owner": "referred business has a distinct primary owner from existing Rho-Bank business accounts",
    "qualifying_new_money": "qualifying deposit is new money rather than a Rho-Bank transfer",
    "deposit_made_within_window": "qualifying deposit is made within the product's deposit window",
    "deposit_held_required_period": "qualifying deposit remains in the account for at least 30 days after the qualifying period ends",
    "no_other_promotion": "referral is not combined with another new-account promotion",
    "one_referral_code": "only one referral code is used",
    "both_accounts_good_standing": "both accounts remain in good standing",
    "referred_verified": "referred business-account applicant is verified",
    "referred_open_personal_checking": "referred applicant has an OPEN personal checking account",
    "referred_personal_balance_at_least_500": "referred applicant's existing checking balance is at least $500",
    "referred_no_closed_accounts": "referred applicant has no CLOSED accounts",
    "referred_business_count_under_6": "referred applicant has fewer than six business checking accounts",
}


def parse_date(value, field):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a YYYY-MM-DD string or null")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid YYYY-MM-DD date") from exc


def parse_timestamp(value):
    if not isinstance(value, str):
        raise ValueError("bonus_timestamps entries must be ISO-8601 strings")
    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("bonus_timestamps entries must be valid ISO-8601 timestamps") from exc
    if parsed.tzinfo is None:
        raise ValueError("bonus_timestamps entries must include a timezone")
    return parsed.astimezone(timezone.utc)


def parse_as_of_timestamp(value):
    if value is None:
        return None
    return parse_timestamp(value)


def state_for_condition(value, field):
    if value is True:
        return "yes"
    if value is False:
        return "no"
    if value is None:
        return "unknown"
    raise ValueError(f"conditions[{field!r}] must be true, false, or null")


def assess(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")

    as_of = parse_date(payload.get("as_of_date"), "as_of_date")
    if as_of is None:
        raise ValueError("as_of_date is required")
    opened = parse_date(payload.get("first_checking_opened"), "first_checking_opened")
    if opened is not None and opened > as_of:
        raise ValueError("first_checking_opened cannot be after as_of_date")

    deposit_raw = payload.get("planned_deposit")
    try:
        deposit = Decimal(str(deposit_raw))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("planned_deposit must be a non-negative number") from exc
    if deposit < 0:
        raise ValueError("planned_deposit must be a non-negative number")

    timestamps_given = "bonus_timestamps" in payload and payload.get("bonus_timestamps") is not None
    timestamps = payload.get("bonus_timestamps", [])
    if timestamps_given and not isinstance(timestamps, list):
        raise ValueError("bonus_timestamps must be an array or null")
    as_of_timestamp = parse_as_of_timestamp(payload.get("as_of_timestamp"))
    if timestamps_given and as_of_timestamp is None:
        raise ValueError("as_of_timestamp with timezone is required when bonus_timestamps is supplied")
    parsed_timestamps = [parse_timestamp(v) for v in timestamps] if timestamps_given else []

    if timestamps_given:
        cutoff = as_of_timestamp - timedelta(days=9)
        rolling_count = sum(1 for timestamp in parsed_timestamps if cutoff <= timestamp <= as_of_timestamp)
        rolling_state = "yes" if rolling_count < 2 else "no"
    else:
        rolling_count = None
        rolling_state = "unknown"

    annual_counts = payload.get("annual_bonus_counts", {})
    if annual_counts is None:
        annual_counts = {}
    if not isinstance(annual_counts, dict):
        raise ValueError("annual_bonus_counts must be an object or null")

    conditions = payload.get("conditions", {})
    if conditions is None:
        conditions = {}
    if not isinstance(conditions, dict):
        raise ValueError("conditions must be an object or null")
    condition_states = {
        key: state_for_condition(conditions.get(key), key) for key in CONDITION_LABELS
    }
    failed_conditions = [CONDITION_LABELS[k] for k, v in condition_states.items() if v == "no"]
    unknown_conditions = [CONDITION_LABELS[k] for k, v in condition_states.items() if v == "unknown"]

    tenure_days = (as_of - opened).days if opened is not None else None
    rows = []
    for product in PRODUCTS:
        if deposit >= Decimal(product["deposit"]):
            deposit_state = "yes"
        else:
            deposit_state = "no"

        if tenure_days is None:
            tenure_state = "unknown"
        elif tenure_days >= product["tenure_days"]:
            tenure_state = "yes"
        else:
            tenure_state = "no"

        supplied_count = annual_counts.get(product["name"])
        if supplied_count is None:
            annual_state = "unknown"
            annual_count = None
        elif isinstance(supplied_count, int) and supplied_count >= 0:
            annual_count = supplied_count
            annual_state = "yes" if annual_count < product["annual_limit"] else "no"
        else:
            raise ValueError(f"annual_bonus_counts[{product['name']!r}] must be a non-negative integer")

        numeric_states = (deposit_state, tenure_state, annual_state, rolling_state)
        numeric_blocked = any(value == "no" for value in numeric_states)
        numeric_unknown = any(value == "unknown" for value in numeric_states)
        prerequisites_blocked = bool(failed_conditions)
        prerequisites_unknown = bool(unknown_conditions)
        if numeric_blocked or prerequisites_blocked:
            overall = "no"
        elif numeric_unknown or prerequisites_unknown:
            overall = "conditional"
        else:
            overall = "yes"

        rows.append({
            "product": product["name"],
            "referrer_bonus": product["bonus"],
            "required_deposit": product["deposit"],
            "deposit_window_days": product["window_days"],
            "required_tenure_days": product["tenure_days"],
            "annual_limit": product["annual_limit"],
            "annual_bonus_count": annual_count,
            "deposit_state": deposit_state,
            "tenure_state": tenure_state,
            "annual_capacity_state": annual_state,
            "rolling_capacity_state": rolling_state,
            "overall_state": overall,
        })

    viable_numeric = [
        row for row in rows
        if row["deposit_state"] == "yes"
        and row["tenure_state"] == "yes"
        and row["annual_capacity_state"] != "no"
        and row["rolling_capacity_state"] != "no"
    ]
    best = max(viable_numeric, key=lambda row: row["referrer_bonus"], default=None)

    # This is useful when an exact opening date or capacity data has not yet
    # been obtained. It never overrides a known blocker and is explicitly
    # labelled conditional rather than an approval.
    potential_rows = [
        row for row in rows
        if row["deposit_state"] == "yes"
        and row["tenure_state"] != "no"
        and row["annual_capacity_state"] != "no"
        and row["rolling_capacity_state"] != "no"
        and not failed_conditions
    ]
    potential = max(potential_rows, key=lambda row: row["referrer_bonus"], default=None)

    return {
        "as_of_date": as_of.isoformat(),
        "planned_deposit": float(deposit),
        "referrer_tenure_days": tenure_days,
        "rolling_window": {
            "limit": 2,
            "window_days": 9,
            "successful_bonus_count": rolling_count,
            "capacity_state": rolling_state,
        },
        "condition_states": condition_states,
        "failed_conditions": failed_conditions,
        "unknown_conditions": unknown_conditions,
        "products": rows,
        "best_numeric_candidate": None if best is None else {
            "product": best["product"],
            "referrer_bonus": best["referrer_bonus"],
            "overall_state": best["overall_state"],
            "notice": "This ranks numeric criteria only; all referral and account-opening prerequisites still must be confirmed.",
        },
        "best_potential_candidate": None if potential is None else {
            "product": potential["product"],
            "referrer_bonus": potential["referrer_bonus"],
            "overall_state": potential["overall_state"],
            "notice": "This is the highest bonus not ruled out by the supplied amount or any known numeric blocker. Unknown tenure, capacity, referral, and account-opening facts make it conditional, not approved.",
        },
    }


def main():
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(assess(payload), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
