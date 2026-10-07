#!/usr/bin/env python3
"""Deterministic internal scoring aid for the documented PIN-lock protocol.
Reads one JSON object from stdin and writes one JSON object to stdout.
"""
import json
import sys
from datetime import datetime, date, timezone


def out(value):
    print(json.dumps(value, separators=(",", ":"), default=str))


def parse_dt(value):
    if not isinstance(value, str) or not value:
        raise ValueError("missing date/time")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.combine(date.fromisoformat(text), datetime.min.time(), tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        # Date-only and timezone-free timestamps may be used for age fields only.
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def same_location(a, b):
    return all(str(a.get(k, "")).strip().casefold() == str(b.get(k, "")).strip().casefold()
               for k in ("city", "state", "country"))


def location_points(location, home):
    if str(location["country"]).casefold() != str(home["country"]).casefold():
        return 3
    if str(location["state"]).casefold() != str(home["state"]).casefold():
        return 2
    if str(location["city"]).casefold() != str(home["city"]).casefold():
        return 1
    return 0


def age_days(now, value):
    return max(0.0, (now - parse_dt(value)).total_seconds() / 86400.0)


def require(data, path, missing):
    cur = data
    try:
        for part in path.split("."):
            cur = cur[part]
    except (KeyError, TypeError):
        missing.append(path)
        return None
    if cur is None or cur == "":
        missing.append(path)
        return None
    return cur


def main(data):
    missing = []
    for field in ("now", "target_card_id", "customer_home.city", "customer_home.state",
                  "customer_home.country", "card.date_issued", "card.daily_atm_limit",
                  "card.prior_pin_locks_90d", "account.date_opened", "account.balance",
                  "account.overdraft_fee_count", "successful_pin_last_used_at",
                  "historical_atm_amounts", "all_cards", "declined_attempts",
                  "identity.standard_verified", "all_locked_cards_assessed"):
        require(data, field, missing)
    declines = data.get("declined_attempts")
    if not isinstance(declines, list) or not declines:
        if "declined_attempts" not in missing:
            missing.append("declined_attempts (at least one normalized declined attempt)")
    if not isinstance(data.get("historical_atm_amounts"), list) or not data.get("historical_atm_amounts"):
        if "historical_atm_amounts" not in missing:
            missing.append("historical_atm_amounts (at least one successful ATM amount)")
    if missing:
        return {"status": "insufficient_data", "missing_fields": sorted(set(missing)),
                "message": "Do not score unknown factors as zero."}
    try:
        now = parse_dt(data["now"])
        home, card, account = data["customer_home"], data["card"], data["account"]
        normalized = []
        for i, attempt in enumerate(declines):
            for key in ("timestamp", "type", "amount", "location"):
                if key not in attempt or attempt[key] is None:
                    raise ValueError("declined_attempts[%d].%s" % (i, key))
            loc = attempt["location"]
            if not all(k in loc and loc[k] not in (None, "") for k in ("city", "state", "country")):
                raise ValueError("declined_attempts[%d].location.city/state/country" % i)
            normalized.append({"timestamp": parse_dt(attempt["timestamp"]), "type": attempt["type"],
                               "amount": abs(float(attempt["amount"])), "location": loc})
        normalized.sort(key=lambda x: x["timestamp"])
    except (ValueError, TypeError, KeyError) as exc:
        return {"status": "insufficient_data", "missing_fields": [str(exc)],
                "message": "Use normalized numeric amounts and ISO dates/timestamps."}

    all_cards = data["all_cards"]
    target = data["target_card_id"]
    automatic = []
    if str(card.get("pin_lock_reason", "")).casefold() == "security_hold":
        automatic.append("security_hold")
    other_locked = any(c.get("card_id") != target and bool(c.get("pin_locked")) for c in all_cards)
    if other_locked:
        automatic.append("other_card_pin_locked")
    recent_stolen = False
    for c in all_cards:
        if str(c.get("issue_reason", "")).casefold() == "stolen" and c.get("date_issued"):
            try:
                recent_stolen = recent_stolen or age_days(now, c["date_issued"]) <= 90
            except ValueError:
                return {"status": "insufficient_data", "missing_fields": ["all_cards[].date_issued"],
                        "message": "A stolen-card issuance date is invalid."}
    if recent_stolen:
        automatic.append("recent_stolen_replacement")

    flags = {}
    # A: maximum mismatch risk across the declined attempts; scatter counts distinct full locations.
    flags["A1_location_mismatch"] = max(location_points(x["location"], home) for x in normalized)
    locations = {(str(x["location"]["city"]).casefold(), str(x["location"]["state"]).casefold(),
                  str(x["location"]["country"]).casefold()) for x in normalized}
    flags["A2_location_scatter"] = 2 if len(locations) >= 3 else (1 if len(locations) == 2 else 0)
    recent_locations = data.get("successful_last_7d_locations", [])
    all_success_home = bool(recent_locations) and all(same_location(x, home) for x in recent_locations)
    any_decline_elsewhere = any(not same_location(x["location"], home) for x in normalized)
    flags["A3_travel_pattern_conflict"] = 1 if all_success_home and any_decline_elsewhere else 0

    hours = [x["timestamp"].hour + x["timestamp"].minute / 60.0 for x in normalized]
    def hour_points(hour):
        if 2 <= hour < 6: return 3
        if 0 <= hour < 2: return 2
        if 22 <= hour < 24: return 1
        return 0
    flags["B1_time_of_day"] = max(hour_points(h) for h in hours)
    days_since_pin = age_days(now, data["successful_pin_last_used_at"])
    flags["B2_since_legitimate_pin_use"] = 2 if days_since_pin > 30 else (1 if days_since_pin > 7 else 0)
    gaps = [(normalized[i]["timestamp"] - normalized[i-1]["timestamp"]).total_seconds() / 60.0
            for i in range(1, len(normalized))]
    min_gap = min(gaps) if gaps else None
    flags["B3_attempt_velocity"] = (0 if min_gap is None or min_gap > 5 else
                                     1 if min_gap >= 2 else 2 if min_gap >= 1 else 3)

    amounts = [x["amount"] for x in normalized]
    flags["C1_amount_pattern"] = 2 if len(amounts) >= 2 and all(amounts[i] < amounts[i-1] for i in range(1, len(amounts))) else 0
    flags["C2_round_number_testing"] = 1 if amounts and all(a > 0 and a % 100 == 0 for a in amounts) else 0
    average_atm = sum(abs(float(x)) for x in data["historical_atm_amounts"]) / len(data["historical_atm_amounts"])
    if average_atm <= 0:
        return {"status": "insufficient_data", "missing_fields": ["historical_atm_amounts (positive average)"],
                "message": "Cannot calculate the historical amount comparison."}
    ratio = max(amounts) / average_atm
    flags["C3_amount_vs_historical_average"] = 2 if ratio > 5 else (1 if ratio > 2 else 0)
    limit = float(card["daily_atm_limit"])
    if limit <= 0:
        return {"status": "insufficient_data", "missing_fields": ["card.daily_atm_limit (positive)"],
                "message": "Cannot calculate ATM-limit comparison."}
    atm_amounts = [x["amount"] for x in normalized if x["type"] == "atm_withdrawal_declined"]
    flags["C4_amount_vs_daily_limit"] = (2 if atm_amounts and sum(atm_amounts) > limit else
                                          1 if atm_amounts and max(atm_amounts) / limit >= .8 else 0)

    locks = int(card["prior_pin_locks_90d"])
    flags["D1_lock_frequency"] = 3 if locks >= 3 else locks
    card_age = age_days(now, card["date_issued"])
    flags["D2_card_age"] = 2 if card_age < 30 else (1 if card_age < 90 else 0)
    other = [c for c in all_cards if c.get("card_id") != target]
    flags["D3_other_card_issues"] = 2 if any(bool(c.get("fraud_alert_active")) for c in other) else (1 if any(bool(c.get("velocity_blocked")) for c in other) else 0)

    account_age = age_days(now, account["date_opened"])
    flags["E1_account_age"] = 2 if account_age < 90 else (1 if account_age < 180 else 0)
    overdrafts = int(account["overdraft_fee_count"])
    flags["E2_overdraft_history"] = 2 if overdrafts >= 2 else (1 if overdrafts == 1 else 0)
    balance = float(account["balance"])
    flags["E3_low_balance_alert"] = 2 if balance < 50 else (1 if balance < 100 else 0)

    answers = data.get("customer_answers") or {}
    questions = []
    # Confirmed location removes all location flags per the protocol wording.
    if answers.get("location_confirmed") is True:
        for key in ("A1_location_mismatch", "A2_location_scatter", "A3_travel_pattern_conflict"):
            flags[key] = 0
    if answers.get("amount_pattern_confirmed") is True:
        flags["C1_amount_pattern"] = 0
    if answers.get("time_confirmed") is True:
        flags["B1_time_of_day"] = 0

    score = sum(flags.values())
    if flags["A1_location_mismatch"] and answers.get("location_confirmed") is None:
        questions.append("location")
    if flags["C1_amount_pattern"] and answers.get("amount_pattern_confirmed") is None:
        questions.append("amount_pattern")
    if flags["B1_time_of_day"] >= 2 and answers.get("time_confirmed") is None:
        questions.append("time_of_day")
    if score < 5:
        questions = []

    level = "LOW" if score <= 4 else "MEDIUM" if score <= 7 else "HIGH" if score <= 10 else "VERY_HIGH" if score <= 14 else "CRITICAL"
    single_three = [name for name, value in flags.items() if value == 3]
    identity = data["identity"]
    decision = "pending_standard_identity_verification" if not identity.get("standard_verified") else "eligible_after_required_verification"
    if "security_hold" in automatic:
        decision = "security_team_transfer_no_unlock"
    elif other_locked and not data["all_locked_cards_assessed"]:
        decision = "complete_all_locked_card_assessments_before_unlock"
    elif locks >= 3:
        decision = "pin_reset_required_no_unlock"
    elif recent_stolen and not identity.get("enhanced_verified"):
        decision = "enhanced_verification_required"
    elif answers.get("said_asleep_at_attempt_time"):
        decision = "critical_security_concern_no_unlock"
    elif single_three:
        decision = "supervisor_review_required_no_unlock"
    elif score >= 15:
        decision = "no_unlock_review_unauthorized_transactions_and_replacement"
    elif score >= 11:
        decision = "no_unlock_callback_or_enhanced_verification_required"
    elif score >= 8:
        decision = "unlock_only_after_confirmation_and_satisfactory_explanation"
    elif score >= 5:
        decision = "unlock_only_after_failed_attempt_confirmation"

    return {"status": "ok", "automatic_triggers": automatic, "flags": flags, "total_score": score,
            "risk_level": level, "single_three_point_flags": single_three,
            "required_questions": questions, "decision": decision,
            "internal_only": True}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("stdin JSON must be an object")
        out(main(payload))
    except Exception as exc:
        out({"status": "invalid_input", "error": str(exc)})
