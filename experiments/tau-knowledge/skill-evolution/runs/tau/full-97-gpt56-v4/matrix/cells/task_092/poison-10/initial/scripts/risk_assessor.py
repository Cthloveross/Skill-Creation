#!/usr/bin/env python3
"""Deterministic PIN-lock fraud-risk helper. Reads JSON stdin, writes JSON stdout."""
import json
import sys
from datetime import datetime, timezone


def dt(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    value = str(value).strip()
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M"):
            try:
                result = datetime.strptime(value, fmt)
                break
            except ValueError:
                result = None
        if result is None:
            return None
    if result.tzinfo is None:
        # The caller must have already interpreted date-only/local values correctly.
        result = result.replace(tzinfo=timezone.utc)
    return result


def num(value):
    try:
        return abs(float(value))
    except (ValueError, TypeError):
        return None


def norm(value):
    return str(value or "").strip().casefold()


def age_days(now, value):
    parsed = dt(value)
    return None if parsed is None else (now - parsed).total_seconds() / 86400.0


def main(data):
    now = dt(data.get("now"))
    if now is None:
        raise ValueError("now must be a valid ISO-8601 or MM/DD/YYYY date")
    home = data.get("customer_address") or {}
    card = data.get("card") or {}
    account = data.get("account") or {}
    declines = data.get("declined_transactions")
    if not isinstance(declines, list):
        raise ValueError("declined_transactions must be a list")
    successes = data.get("successful_transactions", [])
    transactions = data.get("transactions", [])
    other_cards = data.get("other_cards", [])
    flags, unknown, triggers = {}, [], []

    def put(code, points, detail):
        flags[code] = {"points": points, "detail": detail}

    # Automatic triggers.
    if card.get("pin_lock_reason") == "security_hold":
        triggers.append("security_hold")
    if data.get("other_pin_locked_same_account") is True:
        triggers.append("other_card_locked_same_account")
    stolen = data.get("stolen_replacements")
    if stolen is None:
        unknown.append("recent_stolen_replacement")
    else:
        for item in stolen:
            if norm(item.get("issue_reason")) == "stolen":
                days = age_days(now, item.get("date_issued") or item.get("replacement_date"))
                if days is None:
                    unknown.append("recent_stolen_replacement_date")
                elif 0 <= days <= 90:
                    triggers.append("recent_stolen_replacement")
                    break

    # A1/A2 need explicit normalized locations, never heuristic text parsing.
    home_city, home_state, home_country = norm(home.get("city")), norm(home.get("state")), norm(home.get("country"))
    locs = []
    a1_points = []
    if not declines:
        unknown.append("declined_attempts")
    for item in declines:
        loc = item.get("location") or {}
        city, state, country = norm(loc.get("city")), norm(loc.get("state")), norm(loc.get("country"))
        if not (city and state and country and home_city and home_state and home_country):
            unknown.append("decline_location")
            continue
        locs.append((city, state, country))
        if country != home_country:
            a1_points.append(3)
        elif state != home_state:
            a1_points.append(2)
        elif city != home_city:
            a1_points.append(1)
        else:
            a1_points.append(0)
    if a1_points:
        put("A1_location_mismatch", max(a1_points), "highest mismatch among normalized declined locations")
    if locs:
        count = len(set(locs))
        put("A2_location_scatter", 2 if count >= 3 else 1 if count == 2 else 0, "%d distinct locations" % count)

    # A3: all known recent successful locations home, and at least one known decline elsewhere.
    recent_success = []
    for item in successes:
        when = dt(item.get("timestamp") or item.get("date"))
        loc = item.get("location") or {}
        city = norm(loc.get("city"))
        if when is not None and 0 <= (now - when).total_seconds() <= 7 * 86400 and city:
            recent_success.append(city)
    if successes and not recent_success:
        unknown.append("recent_successful_transaction_locations")
    elif recent_success and home_city:
        elsewhere = any(city != home_city for city, _, _ in locs)
        put("A3_travel_pattern_conflict", 1 if all(c == home_city for c in recent_success) and elsewhere else 0,
            "recent success/decline location comparison")

    # B1 and B3 require timestamps, while B2 requires a separately known legitimate PIN use.
    hours, timed_declines = [], []
    for item in declines:
        when = dt(item.get("timestamp"))
        if when is None:
            unknown.append("decline_timestamp")
            continue
        hours.append(when.hour + when.minute / 60.0)
        timed_declines.append(when)
    if hours:
        def time_points(hour):
            if 2 <= hour < 6: return 3
            if 0 <= hour < 2: return 2
            if 22 <= hour < 24: return 1
            return 0
        put("B1_time_of_day", max(time_points(h) for h in hours), "highest-risk declined-attempt time")
    if len(timed_declines) >= 2:
        ordered = sorted(timed_declines)
        minimum = min((b-a).total_seconds() / 60.0 for a, b in zip(ordered, ordered[1:]))
        points = 3 if minimum < 1 else 2 if minimum < 2 else 1 if minimum <= 5 else 0
        put("B3_attempt_velocity", points, "minimum consecutive gap %.2f minutes" % minimum)
    elif declines:
        unknown.append("attempt_velocity")
    last_pin = data.get("last_legitimate_pin_use")
    if last_pin is None:
        unknown.append("last_legitimate_pin_use")
    else:
        days = age_days(now, last_pin)
        if days is None or days < 0:
            unknown.append("last_legitimate_pin_use_date")
        else:
            put("B2_last_legitimate_pin_use", 2 if days > 30 else 1 if days >= 7 else 0, "age in days")

    amounts = [num(x.get("amount")) for x in declines]
    if declines and any(x is None for x in amounts):
        unknown.append("declined_amount")
    amounts = [x for x in amounts if x is not None]
    if amounts:
        decreasing = len(amounts) >= 2 and all(a > b for a, b in zip(amounts, amounts[1:]))
        put("C1_amount_pattern", 2 if decreasing else 0, "decreasing consecutive amounts" if decreasing else "not decreasing")
        put("C2_round_number_testing", 1 if all(a % 100 == 0 for a in amounts) else 0, "all amounts round hundreds" if all(a % 100 == 0 for a in amounts) else "mixed amounts")
    else:
        unknown.append("amount_pattern")

    atm_amounts = [num(x.get("amount")) for x in successes if norm(x.get("type")) == "atm_withdrawal"]
    atm_amounts = [x for x in atm_amounts if x is not None]
    if not atm_amounts:
        unknown.append("successful_atm_withdrawal_average")
    elif amounts:
        average = sum(atm_amounts) / len(atm_amounts)
        ratio = max(amounts) / average if average else None
        if ratio is None:
            unknown.append("successful_atm_withdrawal_average")
        else:
            put("C3_amount_vs_historical_average", 2 if ratio > 5 else 1 if ratio > 2 else 0, "largest attempt versus ATM average")
    limit = num(card.get("daily_atm_limit"))
    if limit is None or limit <= 0:
        unknown.append("daily_atm_limit")
    elif amounts:
        total = sum(amounts)
        points = 2 if total > limit else 1 if max(amounts) / limit > .8 else 0
        put("C4_amount_vs_daily_limit", points, "failed total and largest amount versus daily limit")

    prior = card.get("prior_pin_locks_90d")
    if prior is None:
        unknown.append("prior_pin_locks_90d")
    else:
        prior = int(prior)
        put("D1_lock_frequency", 3 if prior >= 3 else prior, "prior locks in 90 days")
    days = age_days(now, card.get("date_issued"))
    if days is None or days < 0:
        unknown.append("card_age")
    else:
        put("D2_card_age", 2 if days < 30 else 1 if days < 90 else 0, "card active age")
    if other_cards is None:
        unknown.append("other_card_security_issues")
    else:
        fraud = any(bool(x.get("fraud_alert_active")) for x in other_cards)
        velocity = any(bool(x.get("velocity_block")) for x in other_cards)
        put("D3_other_card_issues", 2 if fraud else 1 if velocity else 0, "other-card security status")

    days = age_days(now, account.get("date_opened"))
    if days is None or days < 0:
        unknown.append("account_age")
    else:
        put("E1_account_age", 2 if days < 90 else 1 if days < 180 else 0, "account age")
    if transactions is None:
        unknown.append("overdraft_history")
    else:
        overdrafts = sum(1 for x in transactions if norm(x.get("type")) == "overdraft_fee")
        put("E2_overdraft_history", 2 if overdrafts >= 2 else overdrafts, "%d overdraft fees" % overdrafts)
    balance = num(account.get("balance"))
    if balance is None:
        unknown.append("current_balance")
    else:
        put("E3_low_balance_alert", 2 if balance < 50 else 1 if balance <= 100 else 0, "balance band")

    total = sum(x["points"] for x in flags.values())
    single = any(x["points"] == 3 for x in flags.values())
    if "security_hold" in triggers:
        decision = "cannot_unlock_security_hold"
    elif single or flags.get("D1_lock_frequency", {}).get("points") == 3:
        decision = "supervisor_review_no_ordinary_unlock"
    elif total >= 15:
        decision = "cannot_unlock_review_unauthorized_and_recommend_replacement"
    elif total >= 11:
        decision = "cannot_unlock_callback_or_enhanced_verification"
    elif total >= 8:
        decision = "ask_specific_location_time_questions_before_eligible_unlock"
    elif total >= 5:
        decision = "ask_failed_attempt_ownership_before_eligible_unlock"
    else:
        decision = "eligible_for_standard_unlock_if_all_prerequisites_met"
    return {"automatic_triggers": triggers, "flags": flags, "total_score": total,
            "single_flag_escalation": single, "unknown": sorted(set(unknown)), "decision": decision}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
