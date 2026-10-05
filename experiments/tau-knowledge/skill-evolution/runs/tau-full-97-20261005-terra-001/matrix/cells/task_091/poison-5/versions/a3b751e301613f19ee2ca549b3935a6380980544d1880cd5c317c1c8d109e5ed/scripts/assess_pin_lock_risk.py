#!/usr/bin/env python3
"""Internal PIN-lock fraud assessment helper.

Reads one JSON object from stdin and emits one JSON object on stdout.
Input requires `now` (ISO timestamp), `customer` (home_city, home_state,
home_country, account_opened_at, current_balance), `cards` (array), and optional
`transactions` (array). A card supports card_id, pin_locked, pin_lock_reason,
issue_reason, date_issued, daily_atm_limit, prior_pin_locks_90d,
velocity_blocked, fraud_alert_active, last_legitimate_pin_use_at, and optional
card-specific declined_transactions. Transactions may contain card_id, type,
status, amount, timestamp/date, city/state/country, and description.

Declines are atm_withdrawal_declined or pos_declined. The helper reports absent
facts as missing_data rather than inventing them. It is an internal aid only;
its score and flags must not be disclosed to a customer.
"""
import json
import sys
from datetime import datetime, timezone


def parse_time(value):
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip().replace("Z", "+00:00")
    for form in (None, "%m/%d/%Y", "%Y-%m-%d"):
        try:
            result = datetime.fromisoformat(value) if form is None else datetime.strptime(value, form)
            return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
        except ValueError:
            pass
    return None


def number(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def text(value):
    return str(value or "").strip().casefold()


def age_days(later, earlier):
    return (later - earlier).total_seconds() / 86400


def add(flags, key, points, available=True):
    flags.append({"flag": key, "points": points, "status": "scored" if available else "unavailable"})


def tx_time(tx):
    return parse_time(tx.get("timestamp") or tx.get("date"))


def location(tx):
    return (text(tx.get("city")), text(tx.get("state")), text(tx.get("country")))


def assess(card, cards, customer, transactions, now):
    card_id = card.get("card_id")
    if card.get("pin_locked") is not True:
        return {"card_id": card_id, "decision": "not_pin_locked", "flags": [], "gates": [], "missing_data": []}

    flags, gates, missing, questions = [], [], [], []
    if card.get("pin_lock_reason") == "security_hold":
        gates.append("security_hold_transfer_required")
    if sum(c.get("pin_locked") is True for c in cards) > 1:
        gates.append("all_locked_cards_must_be_reviewed_before_any_unlock")
    for candidate in cards:
        issued = parse_time(candidate.get("date_issued"))
        if candidate.get("issue_reason") == "stolen" and issued and 0 <= age_days(now, issued) <= 90:
            gates.append("enhanced_verification_required_recent_stolen_replacement")
            break

    if "declined_transactions" in card:
        card_transactions = card.get("declined_transactions") or []
    else:
        card_transactions = [t for t in transactions if t.get("card_id") == card_id]
        if any(t.get("type") in ("atm_withdrawal_declined", "pos_declined") for t in transactions) and not card_transactions:
            missing.append("card-specific association for declined transactions")
    declines = [t for t in card_transactions if t.get("type") in ("atm_withdrawal_declined", "pos_declined")]
    if not declines:
        missing.append("declined-attempt details")
    declines.sort(key=lambda t: tx_time(t) or datetime.min.replace(tzinfo=timezone.utc))

    home_city, home_state, home_country = (text(customer.get(k)) for k in ("home_city", "home_state", "home_country"))
    known_locations = [location(t) for t in declines if location(t)[0]]
    if declines and not known_locations:
        missing.append("declined-attempt locations")
    mismatch = 0
    for city, state, country in known_locations:
        mismatch = max(mismatch, 3 if home_country and country and country != home_country else 2 if home_state and state and state != home_state else 1 if home_city and city != home_city else 0)
    add(flags, "A1_location_mismatch", mismatch, bool(known_locations))
    add(flags, "A2_location_scatter", 2 if len(set(known_locations)) >= 3 else 1 if len(set(known_locations)) == 2 else 0, bool(known_locations))
    if mismatch:
        questions.append("location_mismatch")

    successful = [t for t in transactions if t.get("type") in ("atm_withdrawal", "debit_card_purchase") and t.get("status", "posted") == "posted"]
    recent_locations = [location(t) for t in successful if tx_time(t) and 0 <= age_days(now, tx_time(t)) <= 7 and location(t)[0]]
    elsewhere = any(city != home_city for city, _, _ in known_locations) if home_city else False
    if recent_locations and home_city:
        add(flags, "A3_travel_pattern_conflict", 1 if all(city == home_city for city, _, _ in recent_locations) and elsewhere else 0)
    else:
        add(flags, "A3_travel_pattern_conflict", 0, False)
        missing.append("recent successful transaction locations")

    times = [tx_time(t) for t in declines if tx_time(t)]
    if declines and len(times) != len(declines):
        missing.append("declined-attempt timestamps")
    time_score = max((3 if 2 <= t.hour < 6 else 2 if t.hour < 2 else 1 if t.hour >= 22 else 0 for t in times), default=0)
    add(flags, "B1_time_of_day", time_score, bool(times))
    if time_score >= 2:
        questions.append("time_of_day")
    pin_use = parse_time(card.get("last_legitimate_pin_use_at"))
    if pin_use and times:
        delta = age_days(max(times), pin_use)
        add(flags, "B2_time_since_legitimate_pin_use", 2 if delta > 30 else 1 if delta >= 7 else 0)
    else:
        add(flags, "B2_time_since_legitimate_pin_use", 0, False)
        missing.append("last legitimate successful PIN-use timestamp")
    if len(times) >= 2:
        gap = min((b - a).total_seconds() / 60 for a, b in zip(times, times[1:]))
        add(flags, "B3_attempt_velocity", 3 if gap < 1 else 2 if gap < 2 else 1 if gap <= 5 else 0)
    else:
        add(flags, "B3_attempt_velocity", 0, False)

    amounts = [abs(number(t.get("amount"))) for t in declines if number(t.get("amount")) is not None]
    if declines and len(amounts) != len(declines):
        missing.append("declined-attempt amounts")
    decreasing = len(amounts) >= 2 and all(a > b for a, b in zip(amounts, amounts[1:]))
    add(flags, "C1_amount_pattern", 2 if decreasing else 0, bool(amounts))
    if decreasing:
        questions.append("amount_pattern")
    add(flags, "C2_round_number_testing", 1 if amounts and all(a > 0 and a % 100 == 0 for a in amounts) else 0, bool(amounts))
    historical = [abs(number(t.get("amount"))) for t in transactions if t.get("type") == "atm_withdrawal" and t.get("status", "posted") == "posted" and number(t.get("amount")) is not None]
    if historical and amounts:
        average = sum(historical) / len(historical)
        ratio = max(amounts) / average if average else 0
        add(flags, "C3_amount_vs_historical_average", 2 if ratio > 5 else 1 if ratio > 2 else 0)
    else:
        add(flags, "C3_amount_vs_historical_average", 0, False)
        missing.append("successful ATM-withdrawal history")
    limit = number(card.get("daily_atm_limit"))
    atm_amounts = [abs(number(t.get("amount"))) for t in declines if t.get("type") == "atm_withdrawal_declined" and number(t.get("amount")) is not None]
    add(flags, "C4_amount_vs_daily_limit", 2 if limit and sum(atm_amounts) > limit else 1 if limit and atm_amounts and max(atm_amounts) >= .8 * limit else 0, bool(limit and atm_amounts))

    locks = card.get("prior_pin_locks_90d")
    if isinstance(locks, int) and locks >= 0:
        add(flags, "D1_lock_frequency", min(locks, 3))
        if locks >= 3:
            gates.append("pin_reset_required_three_or_more_prior_locks")
    else:
        add(flags, "D1_lock_frequency", 0, False)
        missing.append("prior PIN-lock count in last 90 days")
    issued = parse_time(card.get("date_issued"))
    if issued:
        days = age_days(now, issued)
        add(flags, "D2_card_age", 2 if days < 30 else 1 if days < 90 else 0)
    else:
        add(flags, "D2_card_age", 0, False)
        missing.append("card issue date")
    others = [c for c in cards if c.get("card_id") != card_id]
    add(flags, "D3_other_card_issues", 2 if any(c.get("fraud_alert_active") is True for c in others) else 1 if any(c.get("velocity_blocked") is True for c in others) else 0)

    opened = parse_time(customer.get("account_opened_at"))
    if opened:
        days = age_days(now, opened)
        add(flags, "E1_account_age", 2 if days < 90 else 1 if days < 180 else 0)
    else:
        add(flags, "E1_account_age", 0, False)
        missing.append("account opening date")
    overdrafts = sum(t.get("type") == "overdraft_fee" for t in transactions)
    add(flags, "E2_overdraft_history", 2 if overdrafts >= 2 else overdrafts)
    balance = number(customer.get("current_balance"))
    add(flags, "E3_low_balance", 2 if balance is not None and balance < 50 else 1 if balance is not None and balance < 100 else 0, balance is not None)
    if balance is None:
        missing.append("current account balance")

    total = sum(item["points"] for item in flags)
    three_point = [item["flag"] for item in flags if item["points"] == 3]
    if three_point:
        gates.append("supervisor_review_required_single_three_point_flag")
    if "security_hold_transfer_required" in gates:
        decision = "transfer_security_team"
    elif "pin_reset_required_three_or_more_prior_locks" in gates:
        decision = "pin_reset_required_no_unlock"
    elif total >= 15:
        decision = "cannot_unlock_review_unauthorized_and_recommend_closure_replacement"
    elif total >= 11:
        decision = "cannot_unlock_require_callback_or_enhanced_verification"
    elif three_point:
        decision = "supervisor_review_before_any_unlock"
    elif total >= 8:
        decision = "conditional_unlock_after_location_time_confirmation"
    elif total >= 5:
        decision = "conditional_unlock_after_customer_confirms_attempts"
    else:
        decision = "eligible_for_standard_unlock_if_all_gates_cleared"
    level = "CRITICAL" if total >= 15 else "VERY_HIGH" if total >= 11 else "HIGH" if total >= 8 else "MEDIUM" if total >= 5 else "LOW"
    return {"card_id": card_id, "flags": flags, "total_score": total, "risk_level": level, "decision": decision, "gates": gates, "customer_questions": questions, "missing_data": sorted(set(missing)), "single_three_point_flags": three_point}


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("customer"), dict) or not isinstance(payload.get("cards"), list):
            raise ValueError("expected object with customer object and cards array")
        now = parse_time(payload.get("now"))
        if not now:
            raise ValueError("now must be an ISO-8601 timestamp")
        transactions = payload.get("transactions", [])
        if not isinstance(transactions, list):
            raise ValueError("transactions must be an array")
        cards = [card for card in payload["cards"] if isinstance(card, dict)]
        print(json.dumps({"cards": [assess(card, cards, payload["customer"], transactions, now) for card in cards], "locked_cards_reviewed": sum(card.get("pin_locked") is True for card in cards), "internal_only": True}, separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "internal_only": True}, separators=(",", ":")))


if __name__ == "__main__":
    main()
