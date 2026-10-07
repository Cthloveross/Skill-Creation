#!/usr/bin/env python3
"""Conservative PIN-lock fraud-assessment helper. JSON stdin -> JSON stdout."""
import json
import sys
from datetime import datetime, date, timezone


def parse_dt(value):
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    for fmt in (None, "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.fromisoformat(text) if fmt is None else datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def days_between(later, earlier):
    if not later or not earlier:
        return None
    return (later.date() - earlier.date()).days


def loc_key(loc):
    if not isinstance(loc, dict) or not loc.get("city"):
        return None
    return tuple(str(loc.get(k, "")).strip().lower() for k in ("city", "state", "country"))


def add(flags, unknown, code, value, required=True, note=None):
    if value is None:
        flags[code] = {"points": None, "status": "unknown"}
        if required:
            unknown.append(code + (": " + note if note else ""))
    else:
        flags[code] = {"points": int(value), "status": "scored"}


def main(data):
    now = parse_dt(data.get("now"))
    target_id = data.get("target_card_id")
    cards = data.get("cards") or []
    target = next((c for c in cards if c.get("card_id") == target_id), None)
    if not now or not target:
        print(json.dumps({"complete": False, "error": "now and a matching target_card_id are required"}))
        return
    account = data.get("account") or {}
    attempts = [a for a in (data.get("declined_attempts") or []) if a.get("card_id") == target_id]
    attempts.sort(key=lambda x: parse_dt(x.get("timestamp")) or datetime.min)
    confirmations = data.get("confirmations") or {}
    flags, unknown, triggers = {}, [], []

    # Automatic triggers.
    if target.get("pin_lock_reason") == "security_hold":
        triggers.append("security_hold")
    same_account_locked = [c for c in cards if c.get("account_id") == target.get("account_id") and c.get("card_id") != target_id and c.get("pin_locked") is True]
    if same_account_locked:
        triggers.append("other_card_pin_locked")
    for c in cards:
        issued = parse_dt(c.get("date_issued"))
        if c.get("account_id") == target.get("account_id") and c.get("issue_reason") == "stolen" and days_between(now, issued) is not None and 0 <= days_between(now, issued) <= 90:
            triggers.append("recent_stolen_replacement")
            break

    home = loc_key(data.get("customer_address"))
    attempt_locs = [loc_key(a.get("location")) for a in attempts]
    if not attempts or not home or any(x is None for x in attempt_locs):
        add(flags, unknown, "A1_location_mismatch", None, note="declined attempt location and customer home city/state/country")
        add(flags, unknown, "A2_location_scatter", None, note="structured locations for all declined attempts")
    else:
        mismatch = 0
        for city, state, country in attempt_locs:
            if country != home[2]: mismatch = max(mismatch, 3)
            elif state != home[1]: mismatch = max(mismatch, 2)
            elif city != home[0]: mismatch = max(mismatch, 1)
        add(flags, unknown, "A1_location_mismatch", mismatch)
        nloc = len(set(attempt_locs))
        add(flags, unknown, "A2_location_scatter", 0 if nloc <= 1 else 1 if nloc == 2 else 2)
    successes = data.get("successful_transactions_7d")
    if successes is None or not attempts or not home or any(loc_key(x.get("location")) is None for x in successes):
        add(flags, unknown, "A3_travel_pattern_conflict", None, note="last-7-day successful transaction locations")
    else:
        success_locs = [loc_key(x.get("location")) for x in successes]
        declines_elsewhere = any(x != home for x in attempt_locs if x)
        add(flags, unknown, "A3_travel_pattern_conflict", 1 if success_locs and all(x == home for x in success_locs) and declines_elsewhere else 0)

    times = [parse_dt(a.get("timestamp")) for a in attempts]
    if not attempts or any(t is None for t in times):
        add(flags, unknown, "B1_time_of_day", None, note="timestamps for declined attempts")
    else:
        def hour_points(h):
            return 3 if 2 <= h < 6 else 2 if 0 <= h < 2 else 1 if 22 <= h < 24 else 0
        add(flags, unknown, "B1_time_of_day", max(hour_points(t.hour) for t in times))
    pin_uses = data.get("successful_pin_uses")
    if pin_uses is None or not attempts:
        add(flags, unknown, "B2_since_legitimate_pin_use", None, note="last successful PIN-use timestamp")
    else:
        use_times = [parse_dt(x.get("timestamp")) for x in pin_uses]
        use_times = [x for x in use_times if x]
        if not use_times:
            add(flags, unknown, "B2_since_legitimate_pin_use", None, note="a known last successful PIN use")
        else:
            age = days_between(now, max(use_times))
            add(flags, unknown, "B2_since_legitimate_pin_use", 2 if age > 30 else 1 if age >= 7 else 0)
    if len(times) < 2 or any(t is None for t in times):
        add(flags, unknown, "B3_attempt_velocity", None, note="at least two timestamped declined attempts")
    else:
        minimum = min((b-a).total_seconds()/60 for a, b in zip(times, times[1:]))
        add(flags, unknown, "B3_attempt_velocity", 3 if minimum < 1 else 2 if minimum < 2 else 1 if minimum <= 5 else 0)

    amounts = [abs(float(a["amount"])) for a in attempts if a.get("amount") is not None]
    if len(amounts) < 2:
        add(flags, unknown, "C1_amount_pattern", None, note="amounts for consecutive declined attempts")
    else:
        add(flags, unknown, "C1_amount_pattern", 2 if all(b < a for a, b in zip(amounts, amounts[1:])) else 0)
    if not amounts:
        add(flags, unknown, "C2_round_number_testing", None, note="declined attempt amounts")
    else:
        add(flags, unknown, "C2_round_number_testing", 1 if all(a % 100 == 0 for a in amounts) else 0)
    historical = data.get("successful_atm_withdrawals")
    h_amounts = [abs(float(x["amount"])) for x in (historical or []) if x.get("amount") is not None]
    if not amounts or not h_amounts or sum(h_amounts) == 0:
        add(flags, unknown, "C3_vs_historical_atm_average", None, note="recent successful ATM withdrawal amounts")
    else:
        ratio = max(amounts) / (sum(h_amounts) / len(h_amounts))
        add(flags, unknown, "C3_vs_historical_atm_average", 2 if ratio > 5 else 1 if ratio > 2 else 0)
    limit = target.get("daily_atm_limit")
    if not amounts or limit is None or float(limit) <= 0:
        add(flags, unknown, "C4_vs_daily_atm_limit", None, note="daily ATM limit and declined amounts")
    else:
        add(flags, unknown, "C4_vs_daily_atm_limit", 2 if sum(amounts) > float(limit) else 1 if max(amounts) >= .8 * float(limit) else 0)

    prior = target.get("prior_pin_locks_90d")
    add(flags, unknown, "D1_lock_frequency", None if prior is None else 3 if int(prior) >= 3 else int(prior))
    issued = parse_dt(target.get("date_issued"))
    age = days_between(now, issued)
    add(flags, unknown, "D2_card_age", None if age is None else 2 if age < 30 else 1 if age < 90 else 0)
    other = [c for c in cards if c.get("card_id") != target_id]
    if any("velocity_blocked" not in c or "fraud_alert_active" not in c for c in other):
        add(flags, unknown, "D3_other_card_issues", None, note="security status of all other debit cards")
    else:
        add(flags, unknown, "D3_other_card_issues", 2 if any(c.get("fraud_alert_active") for c in other) else 1 if any(c.get("velocity_blocked") for c in other) else 0)
    opened = parse_dt(account.get("date_opened"))
    account_age = days_between(now, opened)
    add(flags, unknown, "E1_account_age", None if account_age is None else 2 if account_age < 90 else 1 if account_age < 180 else 0)
    fees = data.get("overdraft_fee_count")
    add(flags, unknown, "E2_overdraft_history", None if fees is None else 2 if int(fees) >= 2 else 1 if int(fees) == 1 else 0)
    balance = account.get("balance")
    add(flags, unknown, "E3_low_balance", None if balance is None else 2 if float(balance) < 50 else 1 if float(balance) < 100 else 0)

    # Apply credible customer confirmations only after initial questions have been asked.
    if confirmations.get("location_confirmed"):
        for code in ("A1_location_mismatch", "A2_location_scatter", "A3_travel_pattern_conflict"):
            if flags.get(code, {}).get("points") is not None:
                flags[code] = {"points": 0, "status": "removed_by_customer_confirmation"}
    if confirmations.get("amounts_confirmed") and flags.get("C1_amount_pattern", {}).get("points") is not None:
        flags["C1_amount_pattern"] = {"points": 0, "status": "removed_by_customer_confirmation"}
    if confirmations.get("time_confirmed") and flags.get("B1_time_of_day", {}).get("points") is not None:
        flags["B1_time_of_day"] = {"points": 0, "status": "removed_by_customer_confirmation"}

    known = [x["points"] for x in flags.values() if x["points"] is not None]
    score = sum(known)
    complete = not unknown
    single_three = any(x.get("points") == 3 for x in flags.values())
    level = "incomplete" if not complete else "low" if score <= 4 else "medium" if score <= 7 else "high" if score <= 10 else "very_high" if score <= 14 else "critical"
    questions = []
    if complete and score >= 5:
        if flags["A1_location_mismatch"]["points"] > 0: questions.append("location")
        if flags["C1_amount_pattern"]["points"] > 0: questions.append("amount_pattern")
        if flags["B1_time_of_day"]["points"] >= 2: questions.append("time_of_day")
    critical_denial = bool(confirmations.get("customer_was_asleep"))
    prohibited = "security_hold" in triggers or critical_denial or (prior is not None and int(prior) >= 3) or (complete and score >= 15)
    permitted = complete and not prohibited and not single_three and score <= 10 and not triggers
    path = "resolve_missing_evidence" if not complete else "transfer_security" if prohibited or single_three or score >= 11 else "complete_required_customer_questions" if questions else "protocol_allows_unlock_after_verification"
    print(json.dumps({"complete": complete, "unknown_inputs": unknown, "automatic_triggers": triggers, "flags": flags, "score": score, "risk_level": level, "required_questions": questions, "supervisor_review": single_three, "critical_customer_denial": critical_denial, "unlock_permitted_by_protocol": permitted, "recommended_path": path}, sort_keys=True))


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        main(payload)
    except Exception as exc:
        print(json.dumps({"complete": False, "error": str(exc)}))
