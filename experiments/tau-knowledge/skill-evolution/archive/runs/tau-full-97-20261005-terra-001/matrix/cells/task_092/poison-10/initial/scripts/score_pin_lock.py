#!/usr/bin/env python3
"""Calculate a PIN-lock fraud-risk assessment from normalized, authorized evidence.

Input JSON schema (all money values are positive magnitudes):
{
  "now": "ISO-8601 datetime",
  "card": {
    "card_id": "string", "pin_locked": true, "pin_lock_reason": "string|null",
    "date_issued": "ISO date/datetime", "daily_atm_limit": number|null,
    "prior_pin_locks_90d": integer|null
  },
  "account": {
    "account_id": "string", "home_city": "string|null", "home_state": "string|null",
    "home_country": "string|null", "date_opened": "ISO date/datetime|null",
    "balance": number|null
  },
  "all_cards": [{"card_id": "string", "pin_locked": bool,
                 "issue_reason": "string|null", "date_issued": "ISO date/datetime|null",
                 "velocity_blocked": bool, "fraud_alert_active": bool}],
  "declines": [{"timestamp": "ISO-8601 datetime", "amount": number,
                "location": {"city": "string", "state": "string", "country": "string"},
                "channel": "atm|pos"}],
  "successful_transactions": [{"timestamp": "ISO-8601 datetime", "amount": number,
                "channel": "atm|pos|other",
                "location": {"city": "string", "state": "string", "country": "string"}}],
  "successful_pin_uses": [{"timestamp": "ISO-8601 datetime"}],
  "overdraft_count": integer|null,
  "customer_response": {
    "location_confirmed": bool, "amount_pattern_confirmed": bool,
    "time_confirmed": bool, "time_denied_asleep": bool
  }
}

Structured timestamps and locations are intentionally required where the policy depends
on them. Omit unknown values rather than inventing them. Output contains a flag-score map,
total of non-null flags, missing evidence, automatic triggers, and an internal recommended
protocol state. It does not execute a banking action.
"""
import json
import sys
from datetime import datetime, timezone


def fail(message):
    print(json.dumps({"ok": False, "errors": [message]}))
    raise SystemExit(0)


def as_dict(value, name):
    if not isinstance(value, dict):
        fail(name + " must be an object")
    return value


def as_list(value, name):
    if not isinstance(value, list):
        fail(name + " must be an array")
    return value


def parse_dt(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        result = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y", "%Y-%m-%d"):
            try:
                result = datetime.strptime(text, fmt)
                break
            except ValueError:
                result = None
        if result is None:
            return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def location(event):
    raw = event.get("location")
    return raw if isinstance(raw, dict) else {}


def norm(value):
    return value.strip().casefold() if isinstance(value, str) and value.strip() else None


def same(a, b):
    return a is not None and b is not None and a == b


def day_age(now, then):
    return (now - then).total_seconds() / 86400.0


def set_flag(flags, unknown, key, value, required=True):
    if value is None:
        flags[key] = None
        if required:
            unknown.append(key)
    else:
        flags[key] = int(value)


def main(data):
    data = as_dict(data, "input")
    now = parse_dt(data.get("now"))
    card = as_dict(data.get("card"), "card")
    account = as_dict(data.get("account"), "account")
    all_cards = as_list(data.get("all_cards"), "all_cards")
    declines = as_list(data.get("declines"), "declines")
    successes = as_list(data.get("successful_transactions", []), "successful_transactions")
    pin_uses = as_list(data.get("successful_pin_uses", []), "successful_pin_uses")
    response = data.get("customer_response", {})
    response = response if isinstance(response, dict) else {}
    if now is None:
        fail("now must be a valid ISO-8601 or supported date/time value")

    flags, unknown = {}, []
    automatic = []
    card_id = card.get("card_id")
    if card.get("pin_lock_reason") == "security_hold":
        automatic.append("security_hold_transfer_required")
    if any(c.get("card_id") != card_id and c.get("pin_locked") is True for c in all_cards):
        automatic.append("other_locked_cards_must_be_assessed_first")
    stolen_recent_known = True
    stolen_recent = False
    for other in all_cards:
        if other.get("issue_reason") == "stolen":
            issued = parse_dt(other.get("date_issued"))
            if issued is None:
                stolen_recent_known = False
            elif 0 <= day_age(now, issued) <= 90:
                stolen_recent = True
    if stolen_recent:
        automatic.append("recent_stolen_replacement_enhanced_verification")
    elif not stolen_recent_known:
        unknown.append("recent_stolen_replacement_check")

    # Timestamp/amount validity is essential to all decline-dependent scoring.
    normalized_declines = []
    malformed_declines = False
    for item in declines:
        if not isinstance(item, dict):
            malformed_declines = True
            continue
        stamp = parse_dt(item.get("timestamp"))
        amount = item.get("amount")
        if stamp is None or not isinstance(amount, (int, float)) or amount < 0:
            malformed_declines = True
            continue
        normalized_declines.append((stamp, float(amount), item))
    normalized_declines.sort(key=lambda x: x[0])
    if malformed_declines or not normalized_declines:
        unknown.append("complete_structured_decline_history")

    # A1: worst evidenced mismatch among the failed attempts.
    home_city, home_state, home_country = (norm(account.get(k)) for k in ("home_city", "home_state", "home_country"))
    mismatch_scores = []
    location_complete = bool(normalized_declines) and home_city is not None and home_state is not None and home_country is not None
    for _, _, item in normalized_declines:
        loc = location(item)
        city, state, country = norm(loc.get("city")), norm(loc.get("state")), norm(loc.get("country"))
        if not (city and state and country):
            location_complete = False
            continue
        if country != home_country:
            mismatch_scores.append(3)
        elif state != home_state:
            mismatch_scores.append(2)
        elif city != home_city:
            mismatch_scores.append(1)
        else:
            mismatch_scores.append(0)
    set_flag(flags, unknown, "A1_location_mismatch", max(mismatch_scores) if location_complete else None)

    locations = set()
    for _, _, item in normalized_declines:
        loc = location(item)
        city, state, country = norm(loc.get("city")), norm(loc.get("state")), norm(loc.get("country"))
        if not (city and state and country):
            location_complete = False
        else:
            locations.add((city, state, country))
    scatter = 0 if len(locations) == 1 else (1 if len(locations) == 2 else 2)
    set_flag(flags, unknown, "A2_location_scatter", scatter if location_complete else None)

    # A3 requires structured recent successful locations and complete decline locations.
    recent_successes = []
    success_locations_complete = True
    for item in successes:
        if not isinstance(item, dict):
            success_locations_complete = False
            continue
        stamp = parse_dt(item.get("timestamp"))
        if stamp is None:
            success_locations_complete = False
            continue
        if 0 <= day_age(now, stamp) <= 7:
            loc = location(item)
            city, state, country = norm(loc.get("city")), norm(loc.get("state")), norm(loc.get("country"))
            if not (city and state and country):
                success_locations_complete = False
            else:
                recent_successes.append((city, state, country))
    if not successes:
        success_locations_complete = False
    declines_elsewhere = any(score > 0 for score in mismatch_scores)
    if not (location_complete and success_locations_complete and recent_successes):
        set_flag(flags, unknown, "A3_travel_pattern_conflict", None)
    else:
        all_home = all(loc[0] == home_city for loc in recent_successes)
        varied_travel = len(set(recent_successes)) > 1
        set_flag(flags, unknown, "A3_travel_pattern_conflict", 1 if all_home and declines_elsewhere and not varied_travel else 0)

    # B1 is the highest-risk hour of any decline.
    if normalized_declines:
        def hour_points(hour):
            if 2 <= hour < 6: return 3
            if 0 <= hour < 2: return 2
            if 22 <= hour < 24: return 1
            return 0
        set_flag(flags, unknown, "B1_time_of_day", max(hour_points(x[0].hour) for x in normalized_declines))
    else:
        set_flag(flags, unknown, "B1_time_of_day", None)

    parsed_pin_uses = [parse_dt(x.get("timestamp")) for x in pin_uses if isinstance(x, dict)]
    parsed_pin_uses = [x for x in parsed_pin_uses if x is not None and x <= now]
    if not parsed_pin_uses:
        set_flag(flags, unknown, "B2_since_last_legitimate_pin_use", None)
    else:
        age = day_age(now, max(parsed_pin_uses))
        set_flag(flags, unknown, "B2_since_last_legitimate_pin_use", 2 if age > 30 else (1 if age >= 7 else 0))

    if len(normalized_declines) < 2:
        set_flag(flags, unknown, "B3_attempt_velocity", None)
    else:
        gaps = [(normalized_declines[i][0] - normalized_declines[i-1][0]).total_seconds() / 60.0 for i in range(1, len(normalized_declines))]
        shortest = min(gaps)
        velocity = 3 if shortest < 1 else (2 if shortest < 2 else (1 if shortest <= 5 else 0))
        set_flag(flags, unknown, "B3_attempt_velocity", velocity)

    amounts = [x[1] for x in normalized_declines]
    if len(amounts) < 2:
        set_flag(flags, unknown, "C1_decreasing_amount_pattern", None)
    else:
        set_flag(flags, unknown, "C1_decreasing_amount_pattern", 2 if all(amounts[i] < amounts[i-1] for i in range(1, len(amounts))) else 0)
    if amounts:
        set_flag(flags, unknown, "C2_round_number_testing", 1 if all(a > 0 and a % 100 == 0 for a in amounts) else 0)
    else:
        set_flag(flags, unknown, "C2_round_number_testing", None)

    atm_declines = [a for _, a, item in normalized_declines if item.get("channel") == "atm"]
    atm_successes = []
    for item in successes:
        if isinstance(item, dict) and item.get("channel") == "atm" and isinstance(item.get("amount"), (int, float)) and item.get("amount") > 0:
            atm_successes.append(float(item["amount"]))
    if not atm_declines or not atm_successes:
        set_flag(flags, unknown, "C3_amount_vs_historical_atm_average", None)
    else:
        average = sum(atm_successes) / len(atm_successes)
        ratio = max(atm_declines) / average
        set_flag(flags, unknown, "C3_amount_vs_historical_atm_average", 2 if ratio > 5 else (1 if ratio > 2 else 0))

    limit = card.get("daily_atm_limit")
    if not atm_declines or not isinstance(limit, (int, float)) or limit <= 0:
        set_flag(flags, unknown, "C4_amount_vs_daily_atm_limit", None)
    else:
        total, largest = sum(atm_declines), max(atm_declines)
        c4 = 2 if total > limit else (1 if largest >= 0.8 * limit else 0)
        set_flag(flags, unknown, "C4_amount_vs_daily_atm_limit", c4)

    prior = card.get("prior_pin_locks_90d")
    if not isinstance(prior, int) or prior < 0:
        set_flag(flags, unknown, "D1_lock_frequency", None)
    else:
        set_flag(flags, unknown, "D1_lock_frequency", 3 if prior >= 3 else prior)
    issued = parse_dt(card.get("date_issued"))
    if issued is None or issued > now:
        set_flag(flags, unknown, "D2_card_age", None)
    else:
        age = day_age(now, issued)
        set_flag(flags, unknown, "D2_card_age", 2 if age < 30 else (1 if age < 90 else 0))
    other = [c for c in all_cards if c.get("card_id") != card_id]
    if any(not isinstance(c, dict) or "velocity_blocked" not in c or "fraud_alert_active" not in c for c in other):
        set_flag(flags, unknown, "D3_other_card_issues", None)
    else:
        set_flag(flags, unknown, "D3_other_card_issues", 2 if any(c.get("fraud_alert_active") is True for c in other) else (1 if any(c.get("velocity_blocked") is True for c in other) else 0))

    opened = parse_dt(account.get("date_opened"))
    if opened is None or opened > now:
        set_flag(flags, unknown, "E1_account_age", None)
    else:
        age = day_age(now, opened)
        set_flag(flags, unknown, "E1_account_age", 2 if age < 90 else (1 if age < 180 else 0))
    overdrafts = data.get("overdraft_count")
    set_flag(flags, unknown, "E2_overdraft_history", 2 if isinstance(overdrafts, int) and overdrafts >= 2 else (1 if overdrafts == 1 else (0 if overdrafts == 0 else None)))
    balance = account.get("balance")
    if not isinstance(balance, (int, float)):
        set_flag(flags, unknown, "E3_low_balance_alert", None)
    else:
        set_flag(flags, unknown, "E3_low_balance_alert", 2 if balance < 50 else (1 if balance < 100 else 0))

    # Protocol-authorized customer confirmations remove only the named flag/category.
    if response.get("location_confirmed") is True:
        for key in ("A1_location_mismatch", "A2_location_scatter", "A3_travel_pattern_conflict"):
            if flags.get(key) is not None: flags[key] = 0
    if response.get("amount_pattern_confirmed") is True and flags.get("C1_decreasing_amount_pattern") is not None:
        flags["C1_decreasing_amount_pattern"] = 0
    if response.get("time_confirmed") is True and flags.get("B1_time_of_day") is not None:
        flags["B1_time_of_day"] = 0

    total = sum(v for v in flags.values() if isinstance(v, int))
    three_point_flags = [k for k, v in flags.items() if v == 3]
    incomplete = sorted(set(unknown))
    if response.get("time_denied_asleep") is True:
        protocol = "critical_fraud_concern_no_unlock"
    elif "security_hold_transfer_required" in automatic:
        protocol = "security_transfer_no_unlock"
    elif incomplete:
        protocol = "assessment_incomplete_no_unlock"
    elif prior is not None and prior >= 3:
        protocol = "pin_reset_required_no_unlock"
    elif three_point_flags:
        protocol = "supervisor_review_required"
    elif total >= 15:
        protocol = "critical_no_unlock_review_unauthorized_transactions"
    elif total >= 11:
        protocol = "very_high_no_unlock_callback_or_enhanced_verification"
    elif total >= 8:
        protocol = "high_targeted_confirmation_required"
    elif total >= 5:
        protocol = "medium_customer_confirmation_required"
    else:
        protocol = "low_standard_verification_then_eligible_if_all_cards_complete"

    print(json.dumps({
        "ok": True, "card_id": card_id, "automatic_triggers": automatic,
        "flag_scores": flags, "total_score": total,
        "single_three_point_flags": three_point_flags,
        "incomplete_fields": incomplete, "recommended_protocol": protocol,
        "customer_time_denial_critical": response.get("time_denied_asleep") is True
    }, sort_keys=True))


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail("invalid JSON input: " + str(exc))
    main(raw)
