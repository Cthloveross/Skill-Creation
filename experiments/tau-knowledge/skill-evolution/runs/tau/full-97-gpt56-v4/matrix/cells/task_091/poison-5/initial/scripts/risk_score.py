#!/usr/bin/env python3
"""Score normalized PIN-lock evidence supplied as one JSON object on stdin."""
import json
import sys


def add(flags, missing, key, value):
    if value is None:
        missing.append(key)
        return
    flags[key] = value


def main(data):
    flags, missing = {}, []
    loc = data.get("location_mismatch")
    loc_points = {"same_city": 0, "different_city_same_state": 1,
                  "different_state": 2, "different_country": 3}
    if loc is None:
        missing.append("location_mismatch")
    elif loc in loc_points:
        flags["A1_location_mismatch"] = loc_points[loc]
    else:
        raise ValueError("invalid location_mismatch")

    nloc = data.get("distinct_decline_locations")
    if nloc is None: missing.append("distinct_decline_locations")
    else: flags["A2_location_scatter"] = 0 if nloc <= 1 else 1 if nloc == 2 else 2
    conflict = data.get("home_city_successes_and_declines_elsewhere")
    add(flags, missing, "A3_travel_pattern_conflict", 1 if conflict else 0 if conflict is not None else None)

    hours = data.get("decline_hours")
    if hours is None: missing.append("decline_hours")
    else:
        def hour_score(h):
            if not 0 <= h < 24: raise ValueError("decline hour must be 0..23")
            return 3 if 2 <= h < 6 else 2 if h < 2 else 1 if h >= 22 else 0
        flags["B1_time_of_day"] = max([hour_score(h) for h in hours], default=0)
    days = data.get("last_legitimate_pin_days")
    add(flags, missing, "B2_since_legitimate_pin_use",
        0 if days is not None and days <= 7 else 1 if days is not None and days <= 30 else 2 if days is not None else None)
    gaps = data.get("attempt_gaps_minutes")
    if gaps is None: missing.append("attempt_gaps_minutes")
    else:
        def gap_score(g): return 3 if g < 1 else 2 if g < 2 else 1 if g <= 5 else 0
        flags["B3_attempt_velocity"] = max([gap_score(g) for g in gaps], default=0)

    amounts = data.get("amounts")
    if amounts is None or len(amounts) == 0:
        missing.append("amounts")
    else:
        flags["C1_amount_pattern"] = 2 if len(amounts) >= 2 and all(amounts[i] < amounts[i-1] for i in range(1, len(amounts))) else 0
        flags["C2_round_hundreds"] = 1 if all(a != 0 and a % 100 == 0 for a in amounts) else 0
    avg = data.get("average_successful_atm_amount")
    if avg is None or avg <= 0 or amounts is None or not amounts:
        missing.append("average_successful_atm_amount")
    else:
        ratio = max(amounts) / avg
        flags["C3_amount_vs_average"] = 2 if ratio > 5 else 1 if ratio > 2 else 0
    limit = data.get("daily_atm_limit")
    if limit is None or limit <= 0 or amounts is None:
        missing.append("daily_atm_limit")
    else:
        flags["C4_amount_vs_limit"] = 2 if sum(amounts) > limit else 1 if max(amounts, default=0) >= .8 * limit else 0

    locks = data.get("prior_locks_90d")
    add(flags, missing, "D1_lock_frequency", 0 if locks == 0 else 1 if locks == 1 else 2 if locks == 2 else 3 if locks is not None else None)
    card_days = data.get("card_age_days")
    add(flags, missing, "D2_card_age", 2 if card_days is not None and card_days < 30 else 1 if card_days is not None and card_days < 91 else 0 if card_days is not None else None)
    issue = data.get("other_card_issue")
    issue_points = {"none": 0, "velocity_block": 1, "fraud_alert": 2}
    if issue is None: missing.append("other_card_issue")
    elif issue in issue_points: flags["D3_other_card_issues"] = issue_points[issue]
    else: raise ValueError("invalid other_card_issue")

    acct_days = data.get("account_age_days")
    add(flags, missing, "E1_account_age", 2 if acct_days is not None and acct_days < 91 else 1 if acct_days is not None and acct_days < 183 else 0 if acct_days is not None else None)
    overdrafts = data.get("overdraft_count")
    add(flags, missing, "E2_overdraft_history", 0 if overdrafts == 0 else 1 if overdrafts == 1 else 2 if overdrafts is not None else None)
    balance = data.get("current_balance")
    add(flags, missing, "E3_low_balance", 2 if balance is not None and balance < 50 else 1 if balance is not None and balance <= 100 else 0 if balance is not None else None)

    total = sum(flags.values())
    level = "LOW" if total <= 4 else "MEDIUM" if total <= 7 else "HIGH" if total <= 10 else "VERY_HIGH" if total <= 14 else "CRITICAL"
    result = {"flags": flags, "total": total, "risk_level": level,
              "single_flag_escalation": any(v == 3 for v in flags.values()),
              "pin_reset_required": flags.get("D1_lock_frequency") == 3,
              "missing_inputs": missing}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict): raise ValueError("input must be a JSON object")
        main(payload)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
