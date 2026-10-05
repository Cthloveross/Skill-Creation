#!/usr/bin/env python3
"""Internal PIN-lock fraud assessment. Reads JSON stdin and writes JSON stdout."""
import json
import sys
from datetime import datetime, timezone


def norm(value):
    return str(value or "").strip().casefold()


def parse_dt(value):
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    for fmt in (None, "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            item = datetime.fromisoformat(text) if fmt is None else datetime.strptime(text, fmt)
            if item.tzinfo is not None:
                item = item.astimezone(timezone.utc).replace(tzinfo=None)
            return item
        except (TypeError, ValueError):
            pass
    return None


def amount(value):
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return None


def loc_key(location):
    if not isinstance(location, dict):
        return None
    city, state, country = norm(location.get("city")), norm(location.get("state")), norm(location.get("country"))
    return (city, state, country) if city and state and country else None


def flag(code, points=None, status="scored", note=""):
    return {"code": code, "points": points, "status": status, "internal_note": note}


def main(data):
    unknown = []
    flags = []
    now = parse_dt(data.get("now"))
    target = data.get("target_card") or {}
    cards = data.get("cards")
    account = data.get("account") or {}
    customer = data.get("customer") or {}
    declined = data.get("declined_attempts")
    successes = data.get("successful_transactions")
    transactions = data.get("transactions")
    confirmations = data.get("customer_confirmations") or {}

    def need(label):
        if label not in unknown:
            unknown.append(label)

    def add(code, pts, note, confirmation_key=None, remove_location=False):
        confirmation = confirmations.get(confirmation_key) if confirmation_key else None
        if confirmation == "confirmed":
            flags.append(flag(code, 0, "removed_by_customer_confirmation", "Removed after the required customer confirmation."))
        elif remove_location and confirmations.get("location") == "confirmed":
            flags.append(flag(code, 0, "removed_by_customer_confirmation", "Removed after the required location confirmation."))
        else:
            flags.append(flag(code, pts, "scored", note))

    # Basic integrity checks
    target_id = data.get("target_card_id") or target.get("card_id")
    if not target_id:
        need("target_card_id")
    if target_id and target.get("card_id") and target_id != target.get("card_id"):
        need("matching target_card.card_id")
    if target.get("pin_locked") is not True:
        need("confirmation that target card is currently pin_locked=true")
    if not now:
        need("current assessment timestamp")

    automatic = []
    if "pin_lock_reason" not in target:
        need("target card pin_lock_reason")
    elif norm(target.get("pin_lock_reason")) == "security_hold":
        automatic.append("security_hold")

    if not isinstance(cards, list):
        need("complete list of cards on the linked account")
        cards = []
    else:
        locked_others = [c.get("card_id") for c in cards if c.get("card_id") != target_id and c.get("pin_locked") is True]
        missing_lock_status = any("pin_locked" not in c for c in cards)
        if missing_lock_status:
            need("pin_locked status for every card on the account")
        if locked_others:
            automatic.append("other_locked_cards")

    # Recent stolen replacement trigger
    if not now:
        need("current time to evaluate stolen-card trigger")
    elif not cards:
        pass
    else:
        unknown_issue_dates = False
        stolen_recent = False
        for card in cards:
            if norm(card.get("issue_reason")) == "stolen":
                issued = parse_dt(card.get("date_issued"))
                if not issued:
                    unknown_issue_dates = True
                elif 0 <= (now - issued).days <= 90:
                    stolen_recent = True
        if unknown_issue_dates:
            need("issue date for cards issued due to theft")
        if stolen_recent:
            automatic.append("recent_stolen_replacement")

    # Declined-attempt prerequisite and normalized records
    usable_declines = []
    if not isinstance(declined, list) or not declined:
        need("PIN-related declined attempts for target card")
        declined = []
    for item in declined:
        ts, val, place = parse_dt(item.get("timestamp")), amount(item.get("amount")), loc_key(item.get("location"))
        if not ts:
            need("timestamp for every declined attempt")
        if val is None:
            need("amount for every declined attempt")
        if not place:
            need("city, state, and country for every declined attempt")
        if ts and val is not None and place:
            usable_declines.append((ts, val, place, item))
    usable_declines.sort(key=lambda x: x[0])

    home = (norm(customer.get("home_city")), norm(customer.get("home_state")), norm(customer.get("home_country") or "US"))
    if not all(home):
        need("customer home city, state, and country")

    # A1 maximum geographic discrepancy; confirmation removes all location flags per protocol.
    if usable_declines and all(home):
        levels = []
        for _, _, place, _ in usable_declines:
            if place[2] != home[2]: levels.append(3)
            elif place[1] != home[1]: levels.append(2)
            elif place[0] != home[0]: levels.append(1)
            else: levels.append(0)
        add("A1_location_mismatch", max(levels), "Highest declined-attempt location mismatch.", remove_location=True)
    else:
        flags.append(flag("A1_location_mismatch", None, "unknown", "Cannot compare declined locations to home location."))

    if usable_declines:
        scatter = len({x[2] for x in usable_declines})
        add("A2_location_scatter", 0 if scatter == 1 else 1 if scatter == 2 else 2, "Number of distinct declined-attempt locations.", remove_location=True)
    else:
        flags.append(flag("A2_location_scatter", None, "unknown", "Declined locations unavailable."))

    # A3 requires a populated successful-transaction record for the prior seven days.
    recent_success = []
    if not isinstance(successes, list):
        need("successful transaction history for the prior seven days")
        successes = []
    elif not now:
        pass
    else:
        for s in successes:
            stamp, place = parse_dt(s.get("timestamp")), loc_key(s.get("location"))
            if not stamp or not place:
                need("timestamp and location for successful transactions")
                continue
            if 0 <= (now - stamp).total_seconds() <= 7 * 86400:
                recent_success.append(place)
        if not recent_success:
            need("at least one successful transaction with location in the prior seven days")
    if recent_success and usable_declines and all(home):
        all_home = all(place == home for place in recent_success)
        declines_elsewhere = any(place != home for _, _, place, _ in usable_declines)
        # Multiple successful cities indicates travel; any other pattern has no stated point value.
        traveling = len(set(recent_success)) > 1
        add("A3_travel_pattern_conflict", 1 if all_home and declines_elsewhere else 0,
            "Successful-location pattern compared with declined locations.", remove_location=True)
        if not all_home and not traveling:
            # The protocol gives no positive score for this intermediate pattern; retain zero and note it.
            flags[-1]["internal_note"] = "No specified travel-conflict point condition was met."
    else:
        flags.append(flag("A3_travel_pattern_conflict", None, "unknown", "Seven-day successful location history unavailable."))

    # B1 and B3
    if usable_declines:
        def time_points(hour):
            if 2 <= hour < 6: return 3
            if 0 <= hour < 2: return 2
            if 22 <= hour < 24: return 1
            return 0
        b1 = max(time_points(x[0].hour) for x in usable_declines)
        add("B1_time_of_day", b1, "Highest time-of-day risk among declined attempts.", "time_of_day")
    else:
        flags.append(flag("B1_time_of_day", None, "unknown", "Declined timestamps unavailable."))

    if not isinstance(successes, list) or not now:
        flags.append(flag("B2_since_last_legitimate_pin_use", None, "unknown", "Successful PIN-use history unavailable."))
        need("successful PIN-use history")
    else:
        pins = [parse_dt(s.get("timestamp")) for s in successes if s.get("pin_used") is True and parse_dt(s.get("timestamp"))]
        pins = [p for p in pins if p <= now]
        if not pins:
            flags.append(flag("B2_since_last_legitimate_pin_use", None, "unknown", "No authoritative successful PIN-use timestamp."))
            need("last successful legitimate PIN-use timestamp")
        else:
            days = (now - max(pins)).total_seconds() / 86400
            b2 = 2 if days > 30 else 1 if days >= 7 else 0
            flags.append(flag("B2_since_last_legitimate_pin_use", b2, "scored", "Elapsed time since last successful PIN use."))

    if len(usable_declines) < 2:
        flags.append(flag("B3_attempt_velocity", None, "unknown", "At least two declined timestamps are required."))
        need("at least two declined-attempt timestamps for velocity")
    else:
        shortest = min((usable_declines[i][0] - usable_declines[i-1][0]).total_seconds() for i in range(1, len(usable_declines)))
        b3 = 3 if shortest < 60 else 2 if shortest <= 120 else 1 if shortest <= 300 else 0
        flags.append(flag("B3_attempt_velocity", b3, "scored", "Shortest interval between consecutive declined attempts."))

    # C flags
    if len(usable_declines) < 2:
        flags.append(flag("C1_amount_pattern", None, "unknown", "At least two declined amounts are required."))
        need("at least two declined amounts for amount-pattern review")
    else:
        values = [x[1] for x in usable_declines]
        decreasing = all(values[i] < values[i-1] for i in range(1, len(values)))
        add("C1_amount_pattern", 2 if decreasing else 0, "Strictly decreasing consecutive declined amounts.", "amount_pattern")

    if usable_declines:
        all_round = all(abs(v / 100 - round(v / 100)) < 1e-9 for _, v, _, _ in usable_declines)
        flags.append(flag("C2_round_number_testing", 1 if all_round else 0, "scored", "Whether all declined amounts are exact hundreds."))
    else:
        flags.append(flag("C2_round_number_testing", None, "unknown", "Declined amounts unavailable."))

    atm_successes = []
    if isinstance(successes, list):
        for s in successes:
            if norm(s.get("type")) == "atm_withdrawal" and amount(s.get("amount")) is not None:
                atm_successes.append(amount(s.get("amount")))
    if not atm_successes or not usable_declines:
        flags.append(flag("C3_amount_vs_historical_average", None, "unknown", "Successful ATM-withdrawal history unavailable."))
        need("recent successful ATM withdrawal amounts")
    else:
        avg, attempted = sum(atm_successes) / len(atm_successes), max(x[1] for x in usable_declines)
        if avg <= 0:
            flags.append(flag("C3_amount_vs_historical_average", None, "unknown", "Historical ATM average is not usable."))
            need("positive historical ATM withdrawal average")
        else:
            ratio = attempted / avg
            flags.append(flag("C3_amount_vs_historical_average", 2 if ratio > 5 else 1 if ratio > 2 else 0, "scored", "Largest declined amount compared with successful ATM average."))

    limit = amount(target.get("daily_atm_limit"))
    if limit is None or limit <= 0 or not usable_declines:
        flags.append(flag("C4_amount_vs_daily_limit", None, "unknown", "Daily ATM limit or declined amounts unavailable."))
        need("target card daily ATM withdrawal limit")
    else:
        by_day = {}
        for ts, val, _, _ in usable_declines:
            by_day[ts.date()] = by_day.get(ts.date(), 0) + val
        multi_over = any(total > limit and sum(1 for x in usable_declines if x[0].date() == day) > 1 for day, total in by_day.items())
        maximum = max(x[1] for x in usable_declines)
        if multi_over:
            c4 = 2
        elif maximum <= limit:
            c4 = 1 if maximum >= .8 * limit else 0
        else:
            flags.append(flag("C4_amount_vs_daily_limit", None, "manual_review", "A single attempted amount exceeds the stated limit; no explicit point rule applies."))
            need("manual review of single attempt above daily ATM limit")
            c4 = None
        if c4 is not None:
            flags.append(flag("C4_amount_vs_daily_limit", c4, "scored", "Declined amounts compared with daily ATM limit."))

    # D1-D3
    prior_count = target.get("prior_pin_lock_count_90d")
    if prior_count is None:
        dates = target.get("prior_pin_lock_dates")
        if isinstance(dates, list) and now:
            parsed = [parse_dt(d) for d in dates]
            if any(d is None for d in parsed):
                need("valid dates for all prior PIN locks")
                prior_count = None
            else:
                prior_count = sum(0 <= (now - d).days <= 90 for d in parsed)
        else:
            need("target card prior PIN-lock count during prior 90 days")
    try:
        prior_count = int(prior_count) if prior_count is not None else None
    except (TypeError, ValueError):
        prior_count = None
        need("numeric target card prior PIN-lock count")
    if prior_count is None:
        flags.append(flag("D1_lock_frequency", None, "unknown", "Prior lock frequency unavailable."))
    else:
        d1 = 3 if prior_count >= 3 else prior_count
        flags.append(flag("D1_lock_frequency", d1, "scored", "Prior PIN locks in the preceding 90 days."))

    issued = parse_dt(target.get("date_issued"))
    if not issued or not now:
        flags.append(flag("D2_card_age", None, "unknown", "Card issue date unavailable."))
        need("target card issue date")
    else:
        age = (now - issued).days
        d2 = 2 if age < 30 else 1 if age < 90 else 0
        flags.append(flag("D2_card_age", d2, "scored", "Card age under the protocol bands."))

    if not cards:
        flags.append(flag("D3_other_card_issues", None, "unknown", "Other-card security status unavailable."))
    else:
        others = [c for c in cards if c.get("card_id") != target_id]
        if any("velocity_blocked" not in c or "fraud_alert_active" not in c for c in others):
            flags.append(flag("D3_other_card_issues", None, "unknown", "Other-card velocity/fraud status incomplete."))
            need("velocity-block and fraud-alert status for every other card")
        else:
            d3 = 2 if any(c.get("fraud_alert_active") is True for c in others) else 1 if any(c.get("velocity_blocked") is True for c in others) else 0
            flags.append(flag("D3_other_card_issues", d3, "scored", "Most serious issue on another card."))

    # E1-E3
    opened = parse_dt(account.get("date_opened"))
    if not opened or not now:
        flags.append(flag("E1_account_age", None, "unknown", "Account opening date unavailable."))
        need("account opening date")
    else:
        age = (now - opened).days
        e1 = 2 if age < 90 else 1 if age < 180 else 0
        flags.append(flag("E1_account_age", e1, "scored", "Account age under the protocol bands."))

    if not isinstance(transactions, list):
        flags.append(flag("E2_overdraft_history", None, "unknown", "Transaction history unavailable."))
        need("transaction history including overdraft fees")
    else:
        overdrafts = sum(1 for t in transactions if norm(t.get("type")) == "overdraft_fee")
        flags.append(flag("E2_overdraft_history", 2 if overdrafts >= 2 else overdrafts, "scored", "Count of overdraft-fee transactions supplied."))

    bal = account.get("balance")
    try:
        bal = float(bal)
        e3 = 2 if bal < 50 else 1 if bal < 100 else 0
        flags.append(flag("E3_low_balance_alert", e3, "scored", "Current account balance band."))
    except (TypeError, ValueError):
        flags.append(flag("E3_low_balance_alert", None, "unknown", "Current account balance unavailable."))
        need("current account balance")

    # Assemble decision. Unknown inputs always block unlocking.
    scored = [f for f in flags if isinstance(f.get("points"), int)]
    score = sum(f["points"] for f in scored) if not unknown and len(scored) == 15 else None
    has_three = any(f.get("points") == 3 for f in flags)
    asleep = confirmations.get("time_of_day") == "asleep"
    if score is None:
        level = None
    elif score <= 4: level = "LOW"
    elif score <= 7: level = "MEDIUM"
    elif score <= 10: level = "HIGH"
    elif score <= 14: level = "VERY_HIGH"
    else: level = "CRITICAL"

    questions = []
    if score is not None and score >= 5:
        a1 = next((f for f in flags if f["code"] == "A1_location_mismatch"), {})
        c1 = next((f for f in flags if f["code"] == "C1_amount_pattern"), {})
        b1 = next((f for f in flags if f["code"] == "B1_time_of_day"), {})
        if a1.get("points", 0) > 0:
            locations = sorted({", ".join(filter(None, [x[2][0].title(), x[2][1].upper(), x[2][2].upper()])) for x in usable_declines})
            questions.append({"trigger": "location", "customer_text": "I see your card was locked after failed PIN attempts at " + "; ".join(locations) + ". Were you at that location?"})
        if c1.get("points", 0) > 0:
            values = ", then ".join("${:,.2f}".format(x[1]) for x in usable_declines)
            questions.append({"trigger": "amount_pattern", "customer_text": "The attempts were for " + values + ". Do you remember trying those specific amounts?"})
        if b1.get("points", 0) >= 2:
            times = ", ".join(sorted({x[0].strftime("%I:%M %p").lstrip("0") for x in usable_declines if 0 <= x[0].hour < 6}))
            questions.append({"trigger": "time_of_day", "customer_text": "These attempts occurred at " + times + ". Were you trying to use your card at that time?"})

    cannot = bool(unknown or asleep or "security_hold" in automatic or (prior_count is not None and prior_count >= 3) or has_three or level in ("VERY_HIGH", "CRITICAL"))
    if "security_hold" in automatic:
        step = "transfer_to_security_team"
    elif unknown:
        step = "obtain_missing_data_or_escalate; do_not_unlock"
    elif "other_locked_cards" in automatic:
        step = "complete_individual_assessments_for_all_locked_cards_before_any_unlock"
    elif "recent_stolen_replacement" in automatic:
        step = "enhanced_verification_required_before_any_eligible_action"
    elif asleep or level == "CRITICAL":
        step = "do_not_unlock; review_successful_unauthorized_transactions_and_security_options"
    elif prior_count is not None and prior_count >= 3:
        step = "do_not_unlock; PIN_reset_required"
    elif has_three:
        step = "supervisor_or_security_review_required_before_any_unlock"
    elif level == "VERY_HIGH":
        step = "do_not_unlock; callback_or_enhanced_verification_required"
    elif level == "HIGH":
        step = "ask_specific_questions; unlock_only_after_confirmation_and_satisfactory_explanation"
    elif level == "MEDIUM":
        step = "ask_required_failed_attempt_questions; unlock_only_after_required_confirmation"
    else:
        step = "standard_identity_verification_then_eligible_unlock"

    if prior_count == 0: post = "standard_unlock_no_additional_step"
    elif prior_count == 1: post = "after_unlock_offer_PIN_lock_notifications"
    elif prior_count == 2: post = "after_unlock_offer_PIN_reset"
    elif prior_count is not None: post = "PIN_reset_required_no_unlock"
    else: post = "unknown_until_lock_history_is_retrieved"

    result = {
        "target_card_id": target_id,
        "assessment_complete": not unknown and len(scored) == 15,
        "unknown_inputs": unknown,
        "automatic": automatic,
        "flags": flags,
        "total_score": score,
        "risk_level": level,
        "single_three_point_flag": has_three,
        "customer_time_response_critical": asleep,
        "verification_questions": questions,
        "requires_satisfactory_explanation": level == "HIGH",
        "satisfactory_explanation_recorded": bool(data.get("satisfactory_explanation")),
        "cannot_unlock": cannot,
        "required_next_step": step,
        "post_unlock_requirement": post,
        "suspicious_period": {
            "start": usable_declines[0][0].isoformat() if usable_declines else None,
            "end": usable_declines[-1][0].isoformat() if usable_declines else None,
            "instruction": "If unlock is prohibited, review successful transactions in this period and determine with the customer whether any were unauthorized."
        },
        "customer_message_guardrail": "Do not disclose score, points, internal flags, or scoring calculations."
    }
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Top-level JSON must be an object")
        main(payload)
    except Exception as exc:
        print(json.dumps({"assessment_complete": False, "error": "invalid_assessment_input", "detail": str(exc), "required_next_step": "correct_input_or_escalate; do_not_unlock"}, separators=(",", ":")))
