#!/usr/bin/env python3
"""Internal deterministic PIN-lock fraud assessment.

Input is a JSON object. Required keys for a complete score are card, account,
home_location, declined_attempts, successful_last_7_days, last_legitimate_pin_use,
successful_atm_withdrawals, other_cards, other_cards_locked,
stolen_replacement_within_90_days, and now. Dates/times are ISO-8601 strings.
Declined attempts require time, numeric amount, and location (city/state/country).
Set confirmations.location_confirmed, amount_pattern_confirmed, time_confirmed, or
time_asleep_or_denied only after the matching customer conversation.

Output contains internal flags, raw and adjusted score, risk, blockers, questions,
missing facts, and a recommended path. It never performs a banking action.
"""
import json
import sys
from datetime import datetime, timezone


def dt(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        value = value.replace("Z", "+00:00")
        result = datetime.fromisoformat(value)
        return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def loc_key(location):
    if not isinstance(location, dict):
        return None
    vals = [location.get(k) for k in ("city", "state", "country")]
    if any(not isinstance(x, str) or not x.strip() for x in vals):
        return None
    return tuple(x.strip().casefold() for x in vals)


def age_days(start, end):
    a, b = dt(start), dt(end)
    return None if not a or not b else (b - a).total_seconds() / 86400


def add(flags, code, points, detail=""):
    flags[code] = {"points": points, "detail": detail}


def main(data):
    missing = []
    flags = {}
    blockers = []
    card = data.get("card") if isinstance(data.get("card"), dict) else {}
    account = data.get("account") if isinstance(data.get("account"), dict) else {}
    home = loc_key(data.get("home_location"))
    attempts = data.get("declined_attempts")
    successes = data.get("successful_last_7_days")
    atm_successes = data.get("successful_atm_withdrawals")
    now = dt(data.get("now"))
    confirmations = data.get("confirmations") if isinstance(data.get("confirmations"), dict) else {}

    if not now: missing.append("now")
    if not home: missing.append("home_location.city/state/country")
    if not isinstance(attempts, list) or not attempts: missing.append("declined_attempts")
    if not isinstance(successes, list): missing.append("successful_last_7_days")
    if not isinstance(atm_successes, list): missing.append("successful_atm_withdrawals")
    if not isinstance(data.get("other_cards"), list): missing.append("other_cards")
    for key in ("other_cards_locked", "stolen_replacement_within_90_days"):
        if key not in data: missing.append(key)

    valid_attempts = []
    for i, item in enumerate(attempts if isinstance(attempts, list) else []):
        when = dt(item.get("time")) if isinstance(item, dict) else None
        amount = number(item.get("amount")) if isinstance(item, dict) else None
        where = loc_key(item.get("location")) if isinstance(item, dict) else None
        if not when or amount is None or not where:
            missing.append("declined_attempts[%d].time/amount/location" % i)
        else:
            valid_attempts.append((when, abs(amount), where))
    valid_attempts.sort(key=lambda x: x[0])

    # Automatic conditions are reported independently of score.
    if card.get("pin_lock_reason") == "security_hold":
        blockers.append("security_hold_security_transfer_required")
    if data.get("other_cards_locked") is True:
        blockers.append("other_locked_cards_must_be_investigated_first")
    if data.get("stolen_replacement_within_90_days") is True:
        blockers.append("enhanced_verification_required_recent_stolen_card")

    # A1 and A2
    if valid_attempts and home:
        severities = []
        for _, _, where in valid_attempts:
            if where == home: severities.append(0)
            elif where[2] != home[2]: severities.append(3)
            elif where[1] != home[1]: severities.append(2)
            else: severities.append(1)
        add(flags, "A1_location_mismatch", max(severities), "highest declined-attempt location severity")
        unique = set(x[2] for x in valid_attempts)
        add(flags, "A2_location_scatter", 2 if len(unique) >= 3 else 1 if len(unique) == 2 else 0, "distinct declined locations")
    elif not valid_attempts:
        missing.append("valid declined attempt details")

    # A3 expects caller to supply only successful transactions from the last seven days.
    if isinstance(successes, list) and home and valid_attempts:
        success_locs = []
        for i, item in enumerate(successes):
            place = loc_key(item.get("location")) if isinstance(item, dict) else None
            when = dt(item.get("time")) if isinstance(item, dict) else None
            if not place or not when:
                missing.append("successful_last_7_days[%d].time/location" % i)
            else: success_locs.append(place)
        decline_elsewhere = any(x[2][0] != home[0] for x in valid_attempts)
        add(flags, "A3_travel_pattern_conflict", 1 if success_locs and all(x[0] == home[0] for x in success_locs) and decline_elsewhere else 0)

    # B1 and B3
    if valid_attempts:
        def hour_points(h):
            return 3 if 2 <= h < 6 else 2 if 0 <= h < 2 else 1 if 22 <= h < 24 else 0
        add(flags, "B1_time_of_day", max(hour_points(x[0].hour) for x in valid_attempts), "highest declined-attempt time severity")
        gaps = [(valid_attempts[i][0] - valid_attempts[i-1][0]).total_seconds() / 60 for i in range(1, len(valid_attempts))]
        velocity = 0 if not gaps else (3 if min(gaps) < 1 else 2 if min(gaps) < 2 else 1 if min(gaps) <= 5 else 0)
        add(flags, "B3_attempt_velocity", velocity, "shortest interval between failed attempts")

    last_pin = dt(data.get("last_legitimate_pin_use"))
    if not last_pin or not now:
        missing.append("last_legitimate_pin_use")
    else:
        days = (now - last_pin).total_seconds() / 86400
        add(flags, "B2_time_since_legitimate_pin", 2 if days > 30 else 1 if days >= 7 else 0)

    amounts = [x[1] for x in valid_attempts]
    if amounts:
        decreasing = len(amounts) >= 2 and all(amounts[i] < amounts[i-1] for i in range(1, len(amounts)))
        add(flags, "C1_decreasing_amount_pattern", 2 if decreasing else 0)
        add(flags, "C2_round_hundreds", 1 if all(a > 0 and a % 100 == 0 for a in amounts) else 0)

    historical = [abs(number(x)) for x in atm_successes if number(x) is not None and abs(number(x)) > 0] if isinstance(atm_successes, list) else []
    if not historical:
        missing.append("at least one recent successful ATM withdrawal or documented non-applicability")
    elif amounts:
        avg, attempted = sum(historical) / len(historical), max(amounts)
        ratio = attempted / avg
        add(flags, "C3_amount_vs_atm_average", 2 if ratio > 5 else 1 if ratio > 2 else 0)

    limit = number(card.get("daily_atm_limit"))
    if limit is None or limit <= 0:
        missing.append("card.daily_atm_limit")
    elif amounts:
        total = sum(amounts)
        add(flags, "C4_amount_vs_daily_limit", 2 if total > limit else 1 if max(amounts) >= .8 * limit else 0)

    locks = card.get("prior_pin_locks_90d")
    if not isinstance(locks, int) or locks < 0:
        missing.append("card.prior_pin_locks_90d")
    else:
        add(flags, "D1_lock_frequency", 3 if locks >= 3 else locks)
        if locks >= 3: blockers.append("three_or_more_prior_locks_pin_reset_required")

    card_days = age_days(card.get("date_issued"), data.get("now"))
    if card_days is None: missing.append("card.date_issued")
    else: add(flags, "D2_card_age", 2 if card_days < 30 else 1 if card_days < 90 else 0)

    other = data.get("other_cards") if isinstance(data.get("other_cards"), list) else []
    if isinstance(data.get("other_cards"), list):
        issue = 2 if any(x.get("fraud_alert_active") is True for x in other if isinstance(x, dict)) else 1 if any(x.get("velocity_blocked") is True for x in other if isinstance(x, dict)) else 0
        add(flags, "D3_other_card_issues", issue)

    acct_days = age_days(account.get("date_opened"), data.get("now"))
    if acct_days is None: missing.append("account.date_opened")
    else: add(flags, "E1_account_age", 2 if acct_days < 90 else 1 if acct_days < 180 else 0)
    overdrafts = account.get("overdraft_fees_recent")
    if not isinstance(overdrafts, int) or overdrafts < 0: missing.append("account.overdraft_fees_recent")
    else: add(flags, "E2_overdraft_history", 2 if overdrafts >= 2 else 1 if overdrafts == 1 else 0)
    balance = number(account.get("current_balance"))
    if balance is None: missing.append("account.current_balance")
    else: add(flags, "E3_low_balance", 2 if balance < 50 else 1 if balance < 100 else 0)

    # Permitted confirmation changes occur after flag calculation and are auditable.
    removed = []
    if confirmations.get("location_confirmed") is True:
        for code in ("A1_location_mismatch", "A2_location_scatter", "A3_travel_pattern_conflict"):
            if flags.get(code, {}).get("points", 0): flags[code]["points"] = 0; removed.append(code)
    if confirmations.get("amount_pattern_confirmed") is True and flags.get("C1_decreasing_amount_pattern", {}).get("points", 0):
        flags["C1_decreasing_amount_pattern"]["points"] = 0; removed.append("C1_decreasing_amount_pattern")
    if confirmations.get("time_confirmed") is True and flags.get("B1_time_of_day", {}).get("points", 0):
        flags["B1_time_of_day"]["points"] = 0; removed.append("B1_time_of_day")
    if confirmations.get("time_asleep_or_denied") is True:
        blockers.append("customer_denied_or_was_asleep_for_high_risk_time_no_unlock")

    score = sum(x["points"] for x in flags.values())
    level = "LOW" if score <= 4 else "MEDIUM" if score <= 7 else "HIGH" if score <= 10 else "VERY_HIGH" if score <= 14 else "CRITICAL"
    single_three = [code for code, item in flags.items() if item["points"] == 3]
    if single_three: blockers.append("supervisor_review_required_single_three_point_flag")

    questions = []
    if score >= 5:
        if flags.get("A1_location_mismatch", {}).get("points", 0): questions.append("location")
        if flags.get("C1_decreasing_amount_pattern", {}).get("points", 0): questions.append("amount_pattern")
        if flags.get("B1_time_of_day", {}).get("points", 0) >= 2: questions.append("time_of_day")

    if missing: path = "complete_investigation_before_any_unlock"
    elif "security_hold_security_transfer_required" in blockers: path = "transfer_to_security_team"
    elif score >= 15 or confirmations.get("time_asleep_or_denied") is True: path = "do_not_unlock_review_unauthorized_activity_security_or_replacement"
    elif locks is not None and locks >= 3: path = "do_not_unlock_require_pin_reset"
    elif score >= 11: path = "do_not_unlock_require_callback_or_enhanced_verification"
    elif single_three: path = "supervisor_review_before_any_unlock"
    elif data.get("other_cards_locked") is True: path = "finish_all_locked_card_investigations_before_unlock"
    elif data.get("stolen_replacement_within_90_days") is True: path = "enhanced_verification_then_reassess_unlock_eligibility"
    elif score >= 5 and questions: path = "ask_required_customer_questions_then_recalculate"
    else: path = "eligible_for_authorized_unlock_after_final_prerequisite_check"

    return {"flags": flags, "score": score, "risk_level": level, "single_three_point_flags": single_three, "removed_after_customer_confirmation": removed, "required_questions": questions, "blockers": blockers, "missing": sorted(set(missing)), "recommended_path": path}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict): raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": "invalid_assessment_input", "detail": str(exc)}))
        sys.exit(2)
