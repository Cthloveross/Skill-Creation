#!/usr/bin/env python3
"""Score normalized, per-card PIN-lock evidence from JSON stdin.

Unknown values are reported in missing_inputs and make assessment_complete false.
"""
import json
import sys


def require_nonnegative_number(value, name):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative number")
    return value


def add(flags, missing, flag_name, input_name, value):
    """Store a known flag, or report the normalized input that was absent."""
    if value is None:
        missing.append(input_name)
    else:
        flags[flag_name] = value


def main(d):
    flags, missing = {}, []
    loc_map = {"same_city": 0, "different_city_same_state": 1,
               "different_state": 2, "different_country": 3}
    loc = d.get("location_mismatch")
    if loc is None:
        missing.append("location_mismatch")
    elif loc not in loc_map:
        raise ValueError("invalid location_mismatch")
    else:
        flags["A1_location_mismatch"] = loc_map[loc]

    nloc = d.get("distinct_decline_locations")
    if nloc is None:
        missing.append("distinct_decline_locations")
    else:
        require_nonnegative_number(nloc, "distinct_decline_locations")
        flags["A2_location_scatter"] = 0 if nloc <= 1 else 1 if nloc == 2 else 2

    conflict = d.get("home_city_successes_and_declines_elsewhere")
    if conflict is None:
        missing.append("home_city_successes_and_declines_elsewhere")
    elif not isinstance(conflict, bool):
        raise ValueError("home_city_successes_and_declines_elsewhere must be boolean")
    else:
        flags["A3_travel_pattern_conflict"] = int(conflict)

    hours = d.get("decline_hours")
    if hours is None:
        missing.append("decline_hours")
    elif not isinstance(hours, list):
        raise ValueError("decline_hours must be a list")
    else:
        def hour_points(hour):
            if not isinstance(hour, int) or isinstance(hour, bool) or not 0 <= hour < 24:
                raise ValueError("decline hour must be an integer from 0 through 23")
            return 3 if 2 <= hour < 6 else 2 if hour < 2 else 1 if hour >= 22 else 0
        flags["B1_time_of_day"] = max((hour_points(x) for x in hours), default=0)

    days = d.get("last_legitimate_pin_days")
    if days is not None:
        require_nonnegative_number(days, "last_legitimate_pin_days")
    add(flags, missing, "B2_since_legitimate_pin_use", "last_legitimate_pin_days",
        None if days is None else 0 if days <= 7 else 1 if days <= 30 else 2)

    gaps = d.get("attempt_gaps_minutes")
    if gaps is None:
        missing.append("attempt_gaps_minutes")
    elif not isinstance(gaps, list):
        raise ValueError("attempt_gaps_minutes must be a list")
    else:
        def gap_points(gap):
            require_nonnegative_number(gap, "attempt gap")
            return 3 if gap < 1 else 2 if gap < 2 else 1 if gap <= 5 else 0
        flags["B3_attempt_velocity"] = max((gap_points(x) for x in gaps), default=0)

    amounts = d.get("amounts")
    if not isinstance(amounts, list) or not amounts:
        missing.append("amounts")
        amounts = None
    else:
        for amount in amounts:
            require_nonnegative_number(amount, "amount")
        flags["C1_amount_pattern"] = int(len(amounts) >= 2 and all(
            amounts[i] < amounts[i - 1] for i in range(1, len(amounts)))) * 2
        flags["C2_round_hundreds"] = int(all(a != 0 and a % 100 == 0 for a in amounts))

    average = d.get("average_successful_atm_amount")
    if average is not None:
        require_nonnegative_number(average, "average_successful_atm_amount")
    if average is None or average == 0 or amounts is None:
        missing.append("average_successful_atm_amount")
    else:
        ratio = max(amounts) / average
        flags["C3_amount_vs_average"] = 2 if ratio > 5 else 1 if ratio > 2 else 0

    limit = d.get("daily_atm_limit")
    if limit is not None:
        require_nonnegative_number(limit, "daily_atm_limit")
    if limit is None or limit == 0 or amounts is None:
        missing.append("daily_atm_limit")
    else:
        flags["C4_amount_vs_limit"] = 2 if sum(amounts) > limit else 1 if max(amounts) >= .8 * limit else 0

    locks = d.get("prior_locks_90d")
    if locks is not None:
        require_nonnegative_number(locks, "prior_locks_90d")
    add(flags, missing, "D1_lock_frequency", "prior_locks_90d",
        None if locks is None else 0 if locks == 0 else 1 if locks == 1 else 2 if locks == 2 else 3)

    card_days = d.get("card_age_days")
    if card_days is not None:
        require_nonnegative_number(card_days, "card_age_days")
    add(flags, missing, "D2_card_age", "card_age_days",
        None if card_days is None else 2 if card_days < 30 else 1 if card_days < 91 else 0)

    issue_map = {"none": 0, "velocity_block": 1, "fraud_alert": 2}
    issue = d.get("other_card_issue")
    if issue is None:
        missing.append("other_card_issue")
    elif issue not in issue_map:
        raise ValueError("invalid other_card_issue")
    else:
        flags["D3_other_card_issues"] = issue_map[issue]

    account_days = d.get("account_age_days")
    if account_days is not None:
        require_nonnegative_number(account_days, "account_age_days")
    add(flags, missing, "E1_account_age", "account_age_days",
        None if account_days is None else 2 if account_days < 91 else 1 if account_days < 183 else 0)

    overdrafts = d.get("overdraft_count")
    if overdrafts is not None:
        require_nonnegative_number(overdrafts, "overdraft_count")
    add(flags, missing, "E2_overdraft_history", "overdraft_count",
        None if overdrafts is None else 0 if overdrafts == 0 else 1 if overdrafts == 1 else 2)

    balance = d.get("current_balance")
    if balance is not None:
        require_nonnegative_number(balance, "current_balance")
    add(flags, missing, "E3_low_balance", "current_balance",
        None if balance is None else 2 if balance < 50 else 1 if balance <= 100 else 0)

    total = sum(flags.values())
    complete = not missing
    level = ("LOW" if total <= 4 else "MEDIUM" if total <= 7 else "HIGH" if total <= 10 else "VERY_HIGH" if total <= 14 else "CRITICAL") if complete else "INCOMPLETE"
    print(json.dumps({
        "flags": flags, "total": total, "risk_level": level,
        "assessment_complete": complete,
        "single_flag_escalation": any(v == 3 for v in flags.values()),
        "pin_reset_required": flags.get("D1_lock_frequency") == 3,
        "missing_inputs": missing,
    }, sort_keys=True))


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        main(data)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
