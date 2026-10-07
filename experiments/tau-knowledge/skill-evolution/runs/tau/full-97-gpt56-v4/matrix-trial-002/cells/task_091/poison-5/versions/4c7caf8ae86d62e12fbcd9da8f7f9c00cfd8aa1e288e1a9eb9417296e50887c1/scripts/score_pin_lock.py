#!/usr/bin/env python3
"""Internal PIN-lock fraud assessment helper.

Reads one normalized assessment JSON object from stdin and emits one JSON object
on stdout. This script makes no network calls and cannot unlock, reset, close,
or otherwise change a card or account.
"""
import json
import sys
from datetime import datetime, date, timezone


def fail(message):
    print(json.dumps({"ok": False, "error": message}))
    raise SystemExit(2)


def parse_dt(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    for fmt in (None, "%m/%d/%Y", "%Y-%m-%d"):
        try:
            if fmt is None:
                return datetime.fromisoformat(text)
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    raise ValueError("unsupported date/time: %r" % value)


def age_days(now, then):
    if then is None:
        return None
    # Dates without time intentionally compare calendar dates.
    if now.tzinfo and then.tzinfo is None:
        then = then.replace(tzinfo=now.tzinfo)
    if now.tzinfo is None and then.tzinfo:
        now = now.replace(tzinfo=then.tzinfo)
    return (now - then).total_seconds() / 86400.0


def number(value):
    if value is None:
        return None
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return None


def loc_key(entry):
    loc = entry.get("location") or {}
    city = loc.get("city") or entry.get("city")
    state = loc.get("state") or entry.get("state")
    country = loc.get("country") or entry.get("country")
    if not any((city, state, country)):
        return None
    return tuple(str(x or "").strip().casefold() for x in (city, state, country))


def result(name, points=None, note=None):
    d = {"flag": name, "points": points, "status": "scored" if points is not None else "not_applicable"}
    if note:
        d["basis"] = note
    return d


def main(data):
    if not isinstance(data, dict):
        fail("input must be a JSON object")
    for key in ("now", "card", "account", "declined_attempts"):
        if key not in data:
            fail("missing required field: " + key)
    try:
        now = parse_dt(data["now"])
    except ValueError as exc:
        fail(str(exc))
    if now is None or not isinstance(data["card"], dict) or not isinstance(data["account"], dict):
        fail("now must be a date/time and card/account must be objects")
    declines = data["declined_attempts"]
    successes = data.get("successful_transactions", [])
    if not isinstance(declines, list) or not isinstance(successes, list):
        fail("declined_attempts and successful_transactions must be arrays")

    flags = []
    home = data["account"].get("address") or {}
    home_key = tuple(str(home.get(x) or "").strip().casefold() for x in ("city", "state", "country"))
    dlocs = [loc_key(x) for x in declines if isinstance(x, dict) and loc_key(x)]

    # A1: highest severity among evidenced declined locations.
    if dlocs and any(home_key):
        vals = []
        for city, state, country in dlocs:
            if country and home_key[2] and country != home_key[2]: vals.append(3)
            elif state and home_key[1] and state != home_key[1]: vals.append(2)
            elif city and home_key[0] and city != home_key[0]: vals.append(1)
            else: vals.append(0)
        flags.append(result("A1_location_mismatch", max(vals), "worst declined location relative to home address"))
    else:
        flags.append(result("A1_location_mismatch", note="declined location or home location unavailable"))

    if dlocs:
        n = len(set(dlocs))
        flags.append(result("A2_location_scatter", 0 if n == 1 else 1 if n == 2 else 2, "%d distinct declined locations" % n))
    else:
        flags.append(result("A2_location_scatter", note="no declined locations available"))

    recent_success_locs = []
    for x in successes:
        if not isinstance(x, dict): continue
        try: t = parse_dt(x.get("timestamp", x.get("date")))
        except ValueError: continue
        if t is not None and 0 <= age_days(now, t) <= 7 and loc_key(x): recent_success_locs.append(loc_key(x))
    if dlocs and recent_success_locs and any(home_key):
        all_home = all(x[0] == home_key[0] for x in recent_success_locs if x[0])
        any_elsewhere_decline = any(x[0] and x[0] != home_key[0] for x in dlocs)
        flags.append(result("A3_travel_pattern_conflict", 1 if all_home and any_elsewhere_decline else 0))
    else:
        flags.append(result("A3_travel_pattern_conflict", note="seven-day successful location history unavailable"))

    dts = []
    for x in declines:
        if not isinstance(x, dict): continue
        try: t = parse_dt(x.get("timestamp", x.get("date")))
        except ValueError: continue
        if t is not None: dts.append(t)
    if dts:
        hours = [x.hour + x.minute / 60.0 for x in dts]
        def hour_points(h):
            if 2 <= h < 6: return 3
            if 0 <= h < 2: return 2
            if 22 <= h < 24: return 1
            return 0
        flags.append(result("B1_time_of_day", max(hour_points(h) for h in hours), "highest-risk declined-attempt hour"))
    else:
        flags.append(result("B1_time_of_day", note="declined timestamps unavailable"))

    try: last_pin = parse_dt(data.get("last_successful_pin_use"))
    except ValueError as exc: fail(str(exc))
    days = age_days(now, last_pin) if last_pin else None
    if days is None:
        flags.append(result("B2_since_last_legitimate_pin_use", note="last successful PIN use unavailable"))
    else:
        flags.append(result("B2_since_last_legitimate_pin_use", 2 if days > 30 else 1 if days >= 7 else 0))

    if len(dts) >= 2:
        ordered = sorted(dts)
        minutes = min((b - a).total_seconds() / 60.0 for a, b in zip(ordered, ordered[1:]))
        p = 3 if minutes < 1 else 2 if minutes < 2 else 1 if minutes <= 5 else 0
        flags.append(result("B3_attempt_velocity", p, "shortest interval %.2f minutes" % minutes))
    else:
        flags.append(result("B3_attempt_velocity", note="fewer than two timestamped declined attempts"))

    ordered_declines = []
    for x in declines:
        if not isinstance(x, dict): continue
        amt = number(x.get("amount"))
        try: t = parse_dt(x.get("timestamp", x.get("date")))
        except ValueError: t = None
        if amt is not None: ordered_declines.append((t, amt))
    ordered_declines.sort(key=lambda x: x[0] or datetime.min)
    amounts = [x[1] for x in ordered_declines]
    if len(amounts) >= 2:
        decreasing = all(b < a for a, b in zip(amounts, amounts[1:]))
        flags.append(result("C1_amount_pattern", 2 if decreasing else 0))
    else:
        flags.append(result("C1_amount_pattern", note="fewer than two declined amounts"))
    if amounts:
        flags.append(result("C2_round_number_testing", 1 if all(a > 0 and a % 100 == 0 for a in amounts) else 0))
    else:
        flags.append(result("C2_round_number_testing", note="declined amounts unavailable"))

    atm_amounts = [number(x.get("amount")) for x in successes if isinstance(x, dict) and x.get("type") == "atm_withdrawal"]
    atm_amounts = [x for x in atm_amounts if x is not None]
    if amounts and atm_amounts:
        ratio = max(amounts) / (sum(atm_amounts) / len(atm_amounts)) if sum(atm_amounts) else None
        flags.append(result("C3_amount_vs_historical_average", 2 if ratio and ratio > 5 else 1 if ratio and ratio > 2 else 0))
    else:
        flags.append(result("C3_amount_vs_historical_average", note="declined amount or successful ATM history unavailable"))
    limit = number(data["card"].get("daily_atm_limit"))
    if amounts and limit and limit > 0:
        total = sum(amounts)
        p = 2 if total > limit else 1 if max(amounts) / limit >= .8 else 0
        flags.append(result("C4_amount_vs_daily_limit", p))
    else:
        flags.append(result("C4_amount_vs_daily_limit", note="daily ATM limit or declined amount unavailable"))

    locks = data["card"].get("prior_pin_locks_90d")
    if isinstance(locks, int) and locks >= 0:
        flags.append(result("D1_lock_frequency", 3 if locks >= 3 else locks))
    else: flags.append(result("D1_lock_frequency", note="prior lock count unavailable"))
    try: issued = parse_dt(data["card"].get("date_issued"))
    except ValueError as exc: fail(str(exc))
    card_days = age_days(now, issued) if issued else None
    if card_days is None: flags.append(result("D2_card_age", note="card issue date unavailable"))
    else: flags.append(result("D2_card_age", 2 if card_days < 30 else 1 if card_days < 90 else 0))
    other = data.get("other_cards", [])
    if isinstance(other, list):
        p = (1 if any(isinstance(x, dict) and x.get("velocity_blocked") is True for x in other) else 0) + (2 if any(isinstance(x, dict) and x.get("fraud_alert_active") is True for x in other) else 0)
        flags.append(result("D3_other_card_issues", p))
    else: flags.append(result("D3_other_card_issues", note="other_cards must be an array"))

    try: opened = parse_dt(data["account"].get("date_opened"))
    except ValueError as exc: fail(str(exc))
    account_days = age_days(now, opened) if opened else None
    if account_days is None: flags.append(result("E1_account_age", note="account opening date unavailable"))
    else: flags.append(result("E1_account_age", 2 if account_days < 90 else 1 if account_days < 180 else 0))
    od = data.get("overdraft_fee_count")
    if isinstance(od, int) and od >= 0: flags.append(result("E2_overdraft_history", 2 if od >= 2 else od))
    else: flags.append(result("E2_overdraft_history", note="overdraft count unavailable"))
    bal = number(data["account"].get("balance"))
    if bal is None: flags.append(result("E3_low_balance_alert", note="balance unavailable"))
    else: flags.append(result("E3_low_balance_alert", 2 if bal < 50 else 1 if bal < 100 else 0))

    total = sum(f["points"] for f in flags if f["points"] is not None)
    three_point = [f["flag"] for f in flags if f["points"] == 3]
    if total <= 4: level, route = "LOW", "standard_identity_verification_before_unlock"
    elif total <= 7: level, route = "MEDIUM", "ask_general_failed-attempt_ownership_question"
    elif total <= 10: level, route = "HIGH", "ask_specific_location_and_time_questions; unlock_only_with_confirmation_and_satisfactory_explanation"
    elif total <= 14: level, route = "VERY_HIGH", "do_not_unlock; require_callback_or_enhanced_verification"
    else: level, route = "CRITICAL", "do_not_unlock; review_unauthorized_activity_and_recommend_closure_replacement"
    automatic = []
    if data["card"].get("pin_lock_reason") == "security_hold": automatic.append("security_hold_no_chat_unlock")
    if any(isinstance(x, dict) and x.get("pin_locked") is True for x in other): automatic.append("other_pin_locked_card_complete_all_assessments_first")
    if data.get("stolen_replacement_within_90d") is True: automatic.append("recent_stolen_replacement_enhanced_verification")
    if isinstance(locks, int) and locks >= 3: automatic.append("three_or_more_prior_locks_reset_pin_not_unlock")
    questions = []
    by_name = {f["flag"]: f for f in flags}
    if by_name["A1_location_mismatch"]["points"] not in (None, 0): questions.append("Ask whether the customer was at the declined-attempt location.")
    if by_name["C1_amount_pattern"]["points"] == 2: questions.append("Ask whether the customer remembers the specific declining attempted amounts.")
    if (by_name["B1_time_of_day"]["points"] or 0) >= 2: questions.append("Ask whether the customer was trying to use the card at that time; denial or being asleep is a critical fraud concern.")
    print(json.dumps({"ok": True, "internal_only": True, "total_score": total, "risk_level": level, "required_route": route, "flags": flags, "three_point_flags": three_point, "supervisor_review_required": bool(three_point), "automatic_conditions": automatic, "customer_question_prompts": questions, "incomplete_evidence": [f["flag"] for f in flags if f["points"] is None]}, sort_keys=True))

if __name__ == "__main__":
    try:
        main(json.load(sys.stdin))
    except json.JSONDecodeError:
        fail("stdin must contain valid JSON")
    except Exception as exc:
        fail("assessment error: " + str(exc))
