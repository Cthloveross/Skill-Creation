#!/usr/bin/env python3
"""Assess business-referral eligibility and rank qualifying programs.

Input and output are JSON objects on stdin/stdout.  This program is advisory only:
it performs no account lookup and no banking action.
"""

import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation


REQUIRED_GENERAL_BOOLEANS = (
    "referred_is_new_customer",
    "different_registered_address",
    "different_primary_owner",
    "no_promotion_stacking",
    "referrer_good_standing",
    "referred_good_standing",
)
REQUIRED_PROGRAM_FIELDS = (
    "id",
    "referrer_bonus",
    "deposit_min",
    "deposit_window_days",
    "tenure_days",
    "annual_cap",
)


def parse_time(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 timestamp string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field} is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a UTC offset")
    return parsed


def decimal_value(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number or decimal string")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a number or decimal string") from exc
    if amount < 0:
        raise ValueError(f"{field} cannot be negative")
    return amount


def integer_value(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def money(value):
    return format(value.quantize(Decimal("0.01")), "f")


def main(request):
    if not isinstance(request, dict):
        raise ValueError("request must be a JSON object")

    as_of = parse_time(request.get("as_of"), "as_of")
    deposit = request.get("proposed_deposit")
    general = request.get("general")
    programs = request.get("programs")
    if not isinstance(deposit, dict) or not isinstance(general, dict) or not isinstance(programs, list):
        raise ValueError("proposed_deposit, general, and programs are required")

    amount = decimal_value(deposit.get("amount"), "proposed_deposit.amount")
    within_days = integer_value(deposit.get("within_days"), "proposed_deposit.within_days")
    if not isinstance(deposit.get("new_money"), bool):
        raise ValueError("proposed_deposit.new_money must be boolean")

    unknown_general = []
    failed_general = []
    for field in REQUIRED_GENERAL_BOOLEANS:
        value = general.get(field)
        if not isinstance(value, bool):
            unknown_general.append(field)
        elif not value:
            failed_general.append(field)
    if not deposit["new_money"]:
        failed_general.append("proposed_deposit.new_money")

    tenure = general.get("referrer_checking_tenure_days")
    if isinstance(tenure, bool) or not isinstance(tenure, int) or tenure < 0:
        unknown_general.append("referrer_checking_tenure_days")
        tenure = None

    timestamps = general.get("rolling_bonus_timestamps")
    recent_bonus_count = None
    if not isinstance(timestamps, list):
        unknown_general.append("rolling_bonus_timestamps")
    else:
        parsed_timestamps = []
        for index, timestamp in enumerate(timestamps):
            parsed = parse_time(timestamp, f"rolling_bonus_timestamps[{index}]")
            if parsed > as_of:
                raise ValueError("rolling_bonus_timestamps cannot be in the future")
            parsed_timestamps.append(parsed)
        boundary = as_of - timedelta(days=9)
        recent_bonus_count = sum(boundary <= timestamp <= as_of for timestamp in parsed_timestamps)
        if recent_bonus_count >= 2:
            failed_general.append("rolling_9_day_cap")

    annual_counts = general.get("annual_bonus_counts")
    if not isinstance(annual_counts, dict):
        unknown_general.append("annual_bonus_counts")
        annual_counts = {}

    assessed = []
    for index, program in enumerate(programs):
        if not isinstance(program, dict):
            raise ValueError(f"programs[{index}] must be an object")
        missing = [field for field in REQUIRED_PROGRAM_FIELDS if field not in program]
        if missing:
            raise ValueError(f"programs[{index}] is missing: {', '.join(missing)}")
        product_id = program["id"]
        if not isinstance(product_id, str) or not product_id:
            raise ValueError(f"programs[{index}].id must be a non-empty string")
        bonus = decimal_value(program["referrer_bonus"], f"programs[{index}].referrer_bonus")
        minimum = decimal_value(program["deposit_min"], f"programs[{index}].deposit_min")
        window = integer_value(program["deposit_window_days"], f"programs[{index}].deposit_window_days")
        product_tenure = integer_value(program["tenure_days"], f"programs[{index}].tenure_days")
        cap = integer_value(program["annual_cap"], f"programs[{index}].annual_cap")

        blockers = list(failed_general)
        pending = list(unknown_general)
        if amount < minimum:
            blockers.append("deposit_below_product_minimum")
        if within_days > window:
            blockers.append("deposit_after_product_window")
        if tenure is not None and tenure < product_tenure:
            blockers.append("referrer_tenure_below_product_threshold")

        count = annual_counts.get(product_id)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            pending.append(f"annual_bonus_counts.{product_id}")
        elif count >= cap:
            blockers.append("product_annual_cap_reached")

        assessed.append({
            "id": product_id,
            "referrer_bonus": money(bonus),
            "blockers": sorted(set(blockers)),
            "pending_confirmation": sorted(set(pending)),
            "conditions": [
                "The qualifying deposit must be new money.",
                "The qualifying deposit must remain for at least 30 days after the qualifying period ends.",
                "Both accounts must remain in good standing.",
                "A referred account closed within 90 days may cause bonus clawback.",
                "Only one referral code and no incompatible new-account promotion may be applied.",
            ],
            "qualifies": not blockers and not pending,
        })

    qualified = [item for item in assessed if item["qualifies"]]
    qualified.sort(key=lambda item: (-Decimal(item["referrer_bonus"]), item["id"]))
    recommendation = None
    if qualified:
        top_bonus = qualified[0]["referrer_bonus"]
        recommendation = {
            "objective": "maximize_referrer_bonus",
            "highest_referrer_bonus": top_bonus,
            "product_ids": [item["id"] for item in qualified if item["referrer_bonus"] == top_bonus],
        }

    return {
        "as_of": as_of.isoformat(),
        "rolling_9_day_successful_bonus_count": recent_bonus_count,
        "general_blockers": sorted(set(failed_general)),
        "general_missing_confirmations": sorted(set(unknown_general)),
        "recommendation": recommendation,
        "programs": assessed,
        "warnings": ([] if recommendation else [
            "No recommendation is produced until all general eligibility facts are confirmed and at least one product has no blocker."
        ]),
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
