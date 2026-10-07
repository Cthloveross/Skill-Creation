#!/usr/bin/env python3
"""Score normalized PIN-lock assessment facts. Reads one JSON object from stdin, emits one JSON object."""
import json
import sys
from datetime import datetime, timedelta, timezone

FLAG_NAMES = {
    "A1": "location_mismatch", "A2": "location_scatter", "A3": "travel_pattern_conflict",
    "B1": "time_of_day", "B2": "time_since_legitimate_pin_use", "B3": "attempt_velocity",
    "C1": "amount_pattern", "C2": "round_number_testing", "C3": "amount_vs_historical_atm_average",
    "C4": "amount_vs_daily_atm_limit", "D1": "lock_frequency", "D2": "card_age",
    "D3": "other_card_issues", "E1": "account_age", "E2": "overdraft_history", "E3": "low_balance_alert",
}

def parse_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except ValueError:
        return None

def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)

def norm(value):
    return str(value or "").strip().casefold()

def location_key(item):
    fields = tuple(norm(item.get(k)) for k in ("city", "state", "country"))
    return fields if any(fields) else None

def add(flags, missing, excluded, key, points, evidence, needed=None):
    if key in excluded:
        flags[key] = {"name": FLAG_NAMES[key], "points": 0, "status": "excluded_after_customer_confirmation", "evidence": evidence}
    elif points is None:
        flags[key] = {"name": FLAG_NAMES[key], "points": None, "status": "unresolved", "evidence": evidence}
        if needed:
            missing.append(needed)
    else:
        flags[key] = {"name": FLAG_NAMES[key], "points": points, "status": "scored", "evidence": evidence}

def age_days(now, value):
    dt = parse_time(value)
    return None if not dt else (now - dt).total_seconds() / 86400

def main(data):
    missing = []
    flags = {}
    excluded = set(data.get("exclude_flags") or [])
    now = parse_time(data.get("now"))
    if not now:
        return {"error": "now must be an ISO-8601 timestamp"}
    card, account = data.get("card") or {}, data.get("account") or {}
    declines = [x for x in data.get("declines", []) if isinstance(x, dict) and parse_time(x.get("timestamp"))]
    declines.sort(key=lambda x: parse_time(x["timestamp"]))
    successes = [x for x in data.get("successes", []) if isinstance(x, dict) and parse_time(x.get("timestamp"))]
    all_cards = [x for x in data.get("all_cards", []) if isinstance(x, dict)]
    home = data.get("customer_location") or {}

    triggers = []
    if card.get("pin_lock_reason") == "security_hold": triggers.append("security_hold_no_chat_unlock")
    other_locked = [c for c in all_cards if c.get("pin_locked") is True and c.get("card_id") != card.get("card_id")]
    if other_locked: triggers.append("other_cards_locked_complete_all_assessments_first")
    stolen_recent = False
    for c in all_cards:
        if c.get("issue_reason") == "stolen":
            days = age_days(now, c.get("date_issued"))
            if days is not None and 0 <= days <= 90: stolen_recent = True
    if stolen_recent: triggers.append("recent_stolen_replacement_enhanced_verification")

    # A1/A2
    if not declines:
        add(flags, missing, excluded, "A1", None, "No dated declined attempts supplied.", "declined attempt locations")
        add(flags, missing, excluded, "A2", None, "No dated declined attempts supplied.", "declined attempt locations")
    elif not all(norm(home.get(k)) for k in ("city", "state", "country")):
        add(flags, missing, excluded, "A1", None, "Customer home city/state/country is incomplete.", "customer home location")
        locs = [location_key(x) for x in declines]
        add(flags, missing, excluded, "A2", None if any(x is None for x in locs) else max(0, 1 if len(set(locs)) == 2 else 2 if len(set(locs)) >= 3 else 0), "Distinct declined locations assessed where available.", "declined attempt locations")
    else:
        scores = []
        for x in declines:
            if not all(norm(x.get(k)) for k in ("city", "state", "country")):
                scores = None; break
            if norm(x["country"]) != norm(home["country"]): scores.append(3)
            elif norm(x["state"]) != norm(home["state"]): scores.append(2)
            elif norm(x["city"]) != norm(home["city"]): scores.append(1)
            else: scores.append(0)
        add(flags, missing, excluded, "A1", None if scores is None else max(scores), "Highest mismatch among declined attempts.", "declined attempt locations")
        locs = [location_key(x) for x in declines]
        unique = len(set(locs)) if all(locs) else None
        add(flags, missing, excluded, "A2", None if unique is None else (0 if unique <= 1 else 1 if unique == 2 else 2), "Distinct declined locations: %s." % (unique if unique is not None else "unknown"), "declined attempt locations")

    # A3
    if not declines or not norm(home.get("city")):
        add(flags, missing, excluded, "A3", None, "Need declines and home city.", "recent successful transaction locations and home city")
    else:
        recent = [x for x in successes if parse_time(x["timestamp"]) >= now - timedelta(days=7)]
        if not recent or any(not norm(x.get("city")) for x in recent) or any(not norm(x.get("city")) for x in declines):
            add(flags, missing, excluded, "A3", None, "Need city for seven-day successful transactions and declines.", "recent successful transaction locations")
        else:
            all_home = all(norm(x["city"]) == norm(home["city"]) for x in recent)
            decline_elsewhere = any(norm(x["city"]) != norm(home["city"]) for x in declines)
            add(flags, missing, excluded, "A3", 1 if all_home and decline_elsewhere else 0, "Seven-day success travel comparison.")

    # B1
    if not declines:
        add(flags, missing, excluded, "B1", None, "No dated declines.", "decline timestamps")
    else:
        hours = [parse_time(x["timestamp"]).hour for x in declines]
        def hour_points(h): return 3 if 2 <= h < 6 else 2 if h < 2 else 1 if h >= 22 else 0
        add(flags, missing, excluded, "B1", max(hour_points(h) for h in hours), "Highest-risk local timestamp hour supplied by transaction data.")

    # B2
    pin_successes = [x for x in successes if x.get("pin_used") is True]
    if not pin_successes:
        add(flags, missing, excluded, "B2", None, "No successful PIN-use timestamp supplied.", "last successful PIN use")
    else:
        last = max(parse_time(x["timestamp"]) for x in pin_successes)
        days = (now - last).total_seconds() / 86400
        add(flags, missing, excluded, "B2", 0 if days <= 7 else 1 if days <= 30 else 2, "Days since last PIN use: %.1f." % days)

    # B3
    if len(declines) < 2:
        add(flags, missing, excluded, "B3", None, "Fewer than two dated declines.", "timestamps for consecutive failed attempts")
    else:
        intervals = [(parse_time(b["timestamp"]) - parse_time(a["timestamp"])).total_seconds() / 60 for a, b in zip(declines, declines[1:])]
        shortest = min(intervals)
        pts = 3 if shortest < 1 else 2 if shortest < 2 else 1 if shortest <= 5 else 0
        add(flags, missing, excluded, "B3", pts, "Shortest consecutive-attempt interval: %.2f minutes." % shortest)

    amounts = [x.get("amount") for x in declines]
    if not declines or not all(number(x) for x in amounts):
        for key in ("C1", "C2", "C3", "C4"): add(flags, missing, excluded, key, None, "Declined attempt amounts are incomplete.", "declined attempt amounts")
    else:
        decreasing = len(amounts) >= 2 and all(b < a for a, b in zip(amounts, amounts[1:]))
        add(flags, missing, excluded, "C1", 2 if decreasing else 0, "Amounts assessed in chronological attempt order.")
        add(flags, missing, excluded, "C2", 1 if amounts and all(a % 100 == 0 for a in amounts) else 0, "All attempted amounts tested for exact hundred values.")
        hist = data.get("recent_successful_atm_withdrawals") or []
        hist_amounts = [x.get("amount") if isinstance(x, dict) else x for x in hist]
        if not hist_amounts or not all(number(x) and x >= 0 for x in hist_amounts):
            add(flags, missing, excluded, "C3", None, "No usable successful ATM withdrawal amounts.", "recent successful ATM withdrawal history")
        else:
            avg, attempted = sum(hist_amounts)/len(hist_amounts), max(amounts)
            if avg <= 0: add(flags, missing, excluded, "C3", None, "Historical ATM average is zero or unusable.", "usable historical ATM average")
            else: add(flags, missing, excluded, "C3", 0 if attempted <= 2*avg else 1 if attempted <= 5*avg else 2, "Largest attempt compared with successful ATM average.")
        limit = card.get("daily_atm_limit")
        if not number(limit) or limit <= 0:
            add(flags, missing, excluded, "C4", None, "Daily ATM limit unavailable.", "card daily ATM withdrawal limit")
        else:
            total, largest = sum(amounts), max(amounts)
            add(flags, missing, excluded, "C4", 2 if total > limit else 1 if largest >= .8*limit else 0, "Largest and aggregate attempts compared with daily limit.")

    locks = card.get("prior_pin_locks_90d")
    if not isinstance(locks, int) or locks < 0: add(flags, missing, excluded, "D1", None, "Prior lock count unavailable.", "prior PIN locks in last 90 days")
    else: add(flags, missing, excluded, "D1", 3 if locks >= 3 else locks, "Prior PIN locks: %d." % locks)
    card_days = age_days(now, card.get("date_issued"))
    if card_days is None or card_days < 0: add(flags, missing, excluded, "D2", None, "Card issue date unavailable.", "card issue date")
    else: add(flags, missing, excluded, "D2", 2 if card_days < 30 else 1 if card_days < 90 else 0, "Card age: %.1f days." % card_days)
    others = [c for c in all_cards if c.get("card_id") != card.get("card_id")]
    if not all_cards: add(flags, missing, excluded, "D3", None, "Other-card data unavailable.", "other card security flags")
    else:
        pts = 2 if any(c.get("fraud_alert_active") is True for c in others) else 1 if any(c.get("velocity_blocked") is True for c in others) else 0
        add(flags, missing, excluded, "D3", pts, "Other-card security flags evaluated.")
    account_days = age_days(now, account.get("date_opened"))
    if account_days is None or account_days < 0: add(flags, missing, excluded, "E1", None, "Account opening date unavailable.", "account opening date")
    else: add(flags, missing, excluded, "E1", 2 if account_days < 90 else 1 if account_days < 180 else 0, "Account age: %.1f days." % account_days)
    fees = data.get("overdraft_fee_count")
    if not isinstance(fees, int) or fees < 0: add(flags, missing, excluded, "E2", None, "Overdraft fee count unavailable.", "recent overdraft fee history")
    else: add(flags, missing, excluded, "E2", 2 if fees >= 2 else 1 if fees == 1 else 0, "Overdraft fees: %d." % fees)
    balance = account.get("balance")
    if not number(balance): add(flags, missing, excluded, "E3", None, "Current balance unavailable.", "current account balance")
    else: add(flags, missing, excluded, "E3", 2 if balance < 50 else 1 if balance < 100 else 0, "Current balance assessed.")

    scored = [v["points"] for v in flags.values() if isinstance(v.get("points"), int)]
    total = sum(scored)
    level = "LOW" if total <= 4 else "MEDIUM" if total <= 7 else "HIGH" if total <= 10 else "VERY_HIGH" if total <= 14 else "CRITICAL"
    three = [key for key, value in flags.items() if value.get("points") == 3]
    questions = []
    if total >= 5:
        if flags["A1"].get("points", 0) > 0: questions.append("location_confirmation")
        if flags["C1"].get("points", 0) > 0: questions.append("amount_sequence_confirmation")
        if flags["B1"].get("points", 0) >= 2: questions.append("time_confirmation")
    if locks is not None and isinstance(locks, int) and locks >= 3: protocol = "pin_reset_required_no_unlock"
    elif "security_hold_no_chat_unlock" in triggers: protocol = "security_team_transfer_no_chat_unlock"
    elif missing: protocol = "incomplete_assessment_collect_missing_or_security_review"
    elif total >= 15: protocol = "do_not_unlock_review_unauthorized_successes_closure_replacement_security"
    elif total >= 11: protocol = "do_not_unlock_callback_or_enhanced_verification"
    elif three: protocol = "supervisor_review_required"
    elif total >= 8: protocol = "specific_confirmation_and_satisfactory_explanation_required_before_eligible_unlock"
    elif total >= 5: protocol = "failed_attempt_ownership_confirmation_required_before_eligible_unlock"
    else: protocol = "standard_verification_then_eligible_unlock_if_authorized_capability_exists"
    return {"automatic_triggers": triggers, "flags": flags, "total_score": total, "risk_level": level, "single_flag_escalation": bool(three), "three_point_flags": three, "missing_inputs": sorted(set(missing)), "questions": questions, "recommended_protocol": protocol}

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict): raise ValueError("Input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
