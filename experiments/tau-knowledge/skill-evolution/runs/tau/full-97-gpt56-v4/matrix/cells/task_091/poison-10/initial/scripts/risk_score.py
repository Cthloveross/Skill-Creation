#!/usr/bin/env python3
"""Deterministic internal PIN-lock fraud-risk calculator.
Reads one JSON object from stdin and writes one JSON object to stdout.
"""
import json
import sys
from datetime import datetime, date, timezone


def parse_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    for fmt in (None, "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.fromisoformat(text) if fmt is None else datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def days_between(later, earlier):
    if not later or not earlier:
        return None
    if later.tzinfo and not earlier.tzinfo:
        earlier = earlier.replace(tzinfo=later.tzinfo)
    elif earlier.tzinfo and not later.tzinfo:
        later = later.replace(tzinfo=earlier.tzinfo)
    return (later - earlier).total_seconds() / 86400.0


def number(value):
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return None


def norm(value):
    return str(value or "").strip().casefold()


def location_key(item):
    return (norm(item.get("city")), norm(item.get("state")), norm(item.get("country")))


def main(data):
    now = parse_date(data.get("now"))
    if not now:
        raise ValueError("now is required and must be an ISO-8601 or date value")
    customer = data.get("customer") or {}
    card = data.get("card") or {}
    attempts = list(data.get("declined_attempts") or [])
    successes7 = list(data.get("successful_transactions_7d") or [])
    pin_uses = list(data.get("successful_pin_uses") or [])
    atm_successes = list(data.get("successful_atm_withdrawals") or [])
    cards = list(data.get("account_cards") or [])
    missing = []
    flags = []

    def add(code, points, rationale, applicable=True):
        if applicable:
            flags.append({"code": code, "points": points, "rationale": rationale})

    # Automatic triggers are reported separately from numerical risk flags.
    triggers = []
    if norm(card.get("pin_lock_reason")) == "security_hold":
        triggers.append("security_hold_transfer_required")
    current_id = card.get("card_id")
    if any(bool(c.get("pin_locked")) and c.get("card_id") != current_id for c in cards):
        triggers.append("other_pin_locked_cards_complete_all_reviews_first")
    recent_stolen = False
    for c in cards:
        if norm(c.get("issue_reason")) == "stolen":
            age = days_between(now, parse_date(c.get("date_issued")))
            if age is not None and 0 <= age <= 90:
                recent_stolen = True
    if recent_stolen:
        triggers.append("recent_stolen_replacement_enhanced_verification_required")

    home_city, home_state, home_country = (norm(customer.get("address_city")),
                                            norm(customer.get("address_state")),
                                            norm(customer.get("address_country") or "US"))
    if not attempts:
        missing.append("declined_attempts")
    elif not home_city or not home_state:
        missing.append("customer.address_city and customer.address_state")
    else:
        mismatch = 0
        for a in attempts:
            city, state, country = location_key(a)
            if not city or not state:
                continue
            if country and country != home_country:
                mismatch = max(mismatch, 3)
            elif state != home_state:
                mismatch = max(mismatch, 2)
            elif city != home_city:
                mismatch = max(mismatch, 1)
        add("A1_location_mismatch", mismatch, "Most severe declined-attempt location mismatch")
        locations = {location_key(a) for a in attempts if location_key(a)[0]}
        scatter = 2 if len(locations) >= 3 else 1 if len(locations) == 2 else 0
        add("A2_location_scatter", scatter, "Number of distinct declined-attempt locations")
        if successes7:
            success_cities = [norm(x.get("city")) for x in successes7 if norm(x.get("city"))]
            decline_elsewhere = any(norm(a.get("city")) and norm(a.get("city")) != home_city for a in attempts)
            travel_conflict = 1 if success_cities and all(c == home_city for c in success_cities) and decline_elsewhere else 0
            add("A3_travel_pattern_conflict", travel_conflict, "Recent successful-location pattern")
        else:
            missing.append("successful_transactions_7d")

    parsed_attempts = []
    for a in attempts:
        stamp = parse_date(a.get("timestamp"))
        if stamp:
            parsed_attempts.append((stamp, a))
    parsed_attempts.sort(key=lambda pair: pair[0])
    if attempts and not parsed_attempts:
        missing.append("declined_attempts[].timestamp")
    if parsed_attempts:
        time_points = 0
        for stamp, _ in parsed_attempts:
            hour = stamp.hour
            points = 3 if 2 <= hour < 6 else 2 if 0 <= hour < 2 else 1 if 22 <= hour < 24 else 0
            time_points = max(time_points, points)
        add("B1_time_of_day", time_points, "Most severe declined-attempt time band")
        gaps = []
        for (first, _), (second, _) in zip(parsed_attempts, parsed_attempts[1:]):
            gap = (second - first).total_seconds() / 60.0
            if gap >= 0:
                gaps.append(gap)
        if gaps:
            smallest = min(gaps)
            velocity = 3 if smallest < 1 else 2 if smallest < 2 else 1 if smallest <= 5 else 0
            add("B3_attempt_velocity", velocity, "Shortest interval between consecutive failed attempts")
        else:
            add("B3_attempt_velocity", 0, "Fewer than two timestamped failed attempts")
    if pin_uses:
        use_times = [parse_date(x.get("timestamp")) for x in pin_uses]
        use_times = [x for x in use_times if x]
        if use_times:
            elapsed = days_between(now, max(use_times))
            b2 = 2 if elapsed is not None and elapsed > 30 else 1 if elapsed is not None and elapsed >= 7 else 0
            add("B2_time_since_legitimate_pin_use", b2, "Elapsed time since last successful PIN use")
        else:
            missing.append("successful_pin_uses[].timestamp")
    else:
        missing.append("successful_pin_uses")

    amounts = [number(a.get("amount")) for a in attempts]
    amounts = [x for x in amounts if x is not None]
    if attempts and not amounts:
        missing.append("declined_attempts[].amount")
    if amounts:
        if len(amounts) >= 2 and all(amounts[i] > amounts[i + 1] for i in range(len(amounts) - 1)):
            c1 = 2
        else:
            c1 = 0
        add("C1_amount_pattern", c1, "Decreasing consecutive failed-attempt amounts")
        all_hundreds = all(abs(x / 100.0 - round(x / 100.0)) < 1e-9 for x in amounts)
        add("C2_round_number_testing", 1 if all_hundreds else 0, "Whether all attempted amounts are whole hundreds")
        averages = [number(x.get("amount")) for x in atm_successes]
        averages = [x for x in averages if x is not None and x > 0]
        if averages:
            average = sum(averages) / len(averages)
            ratio = max(amounts) / average
            c3 = 2 if ratio > 5 else 1 if ratio > 2 else 0
            add("C3_amount_vs_historical_average", c3, "Largest attempted amount relative to average successful ATM withdrawal")
        else:
            missing.append("successful_atm_withdrawals")
        limit = number(card.get("daily_atm_limit"))
        if limit and limit > 0:
            total = sum(amounts)
            c4 = 2 if total > limit else 1 if max(amounts) >= .8 * limit else 0
            add("C4_amount_vs_daily_limit", c4, "Attempted amount(s) relative to daily ATM limit")
        else:
            missing.append("card.daily_atm_limit")

    prior = card.get("prior_locks_90d")
    try:
        prior = int(prior)
        d1 = 3 if prior >= 3 else prior if prior in (1, 2) else 0
        add("D1_lock_frequency", d1, "Prior PIN locks in last 90 days")
    except (TypeError, ValueError):
        missing.append("card.prior_locks_90d")
        prior = None
    card_age = days_between(now, parse_date(card.get("date_issued")))
    if card_age is None:
        missing.append("card.date_issued")
    else:
        d2 = 2 if card_age < 30 else 1 if card_age < 90 else 0
        add("D2_card_age", d2, "Card active age")
    other = [c for c in cards if c.get("card_id") != current_id]
    if cards:
        fraud = any(bool(c.get("fraud_alert_active")) or norm(c.get("security_flag")) == "fraud_alert" for c in other)
        velocity = any(bool(c.get("velocity_block")) or norm(c.get("security_flag")) == "velocity_block" for c in other)
        add("D3_other_card_issues", 2 if fraud else 1 if velocity else 0, "Most severe other-card security issue")
    else:
        missing.append("account_cards")

    account_age = days_between(now, parse_date(customer.get("account_opened")))
    if account_age is None:
        missing.append("customer.account_opened")
    else:
        add("E1_account_age", 2 if account_age < 90 else 1 if account_age < 180 else 0, "Account age")
    try:
        overdrafts = int(customer.get("overdraft_count"))
        add("E2_overdraft_history", 2 if overdrafts >= 2 else 1 if overdrafts == 1 else 0, "Recent overdraft fee count")
    except (TypeError, ValueError):
        missing.append("customer.overdraft_count")
    balance = customer.get("current_balance")
    try:
        balance = float(balance)
        add("E3_low_balance_alert", 2 if balance < 50 else 1 if balance < 100 else 0, "Current account balance band")
    except (TypeError, ValueError):
        missing.append("customer.current_balance")

    # Apply only protocol-authorized removals after customer responses.
    remove = set()
    if data.get("confirmed_location_attempts_mine") is True:
        remove.update(("A1_location_mismatch", "A2_location_scatter", "A3_travel_pattern_conflict"))
    if data.get("confirmed_amount_pattern_mine") is True:
        remove.add("C1_amount_pattern")
    if data.get("confirmed_time_attempt_mine") is True:
        remove.add("B1_time_of_day")
    if remove:
        for item in flags:
            if item["code"] in remove:
                item["removed_after_customer_confirmation"] = True
                item["points"] = 0

    total = sum(item["points"] for item in flags)
    tier = "LOW" if total <= 4 else "MEDIUM" if total <= 7 else "HIGH" if total <= 10 else "VERY_HIGH" if total <= 14 else "CRITICAL"
    three_point = [item["code"] for item in flags if item["points"] == 3]
    asleep = data.get("customer_was_asleep_at_attempt_time") is True
    cannot_unlock = ("security_hold_transfer_required" in triggers or (prior is not None and prior >= 3)
                     or tier in ("VERY_HIGH", "CRITICAL") or asleep)
    if "security_hold_transfer_required" in triggers:
        protocol = "transfer_to_security_team"
    elif asleep or tier == "CRITICAL":
        protocol = "do_not_unlock_check_unauthorized_successes_recommend_closure_replacement"
    elif prior is not None and prior >= 3:
        protocol = "do_not_unlock_pin_reset_required"
    elif tier == "VERY_HIGH":
        protocol = "do_not_unlock_require_callback_or_enhanced_verification"
    elif three_point:
        protocol = "supervisor_review_required_before_any_unlock"
    elif tier == "HIGH":
        protocol = "ask_specific_location_and_time_questions_then_recalculate"
    elif tier == "MEDIUM":
        protocol = "ask_whether_failed_attempts_were_customer_s_before_unlock"
    else:
        protocol = "eligible_for_standard_verified_unlock_if_all_other_prerequisites_met"
    if "other_pin_locked_cards_complete_all_reviews_first" in triggers and not cannot_unlock:
        protocol += "; complete_all_locked_card_reviews_before_unlock"

    return {
        "automatic_triggers": triggers,
        "flags": flags,
        "total_score": total,
        "risk_level": tier,
        "single_three_point_flags": three_point,
        "supervisor_review_required": bool(three_point),
        "customer_reported_asleep": asleep,
        "cannot_unlock_from_current_assessment": cannot_unlock,
        "recommended_protocol": protocol,
        "missing_inputs": sorted(set(missing)),
        "internal_use_only": "Do not disclose the score, flags, or calculations to the customer."
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True, separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "error_type": type(exc).__name__}), flush=True)
        sys.exit(2)
