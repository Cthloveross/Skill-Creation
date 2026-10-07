#!/usr/bin/env python3
"""Deterministic internal calculator for the PIN-lock fraud protocol.

Reads one JSON object from stdin and writes one JSON object to stdout. See SKILL.md
for the schema. It intentionally produces no customer-facing score explanation.
"""
import json
import sys
from datetime import datetime, timedelta, timezone


def parse_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return None
        return dt
    except (TypeError, ValueError):
        return None


def parse_date(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.fromisoformat(value + "T00:00:00+00:00")
        except ValueError:
            return None


def norm(value):
    return str(value or "").strip().casefold()


def loc_key(item):
    return (norm(item.get("city")), norm(item.get("state")), norm(item.get("country")))


def same_location(a, b):
    return loc_key(a) == loc_key(b)


def add(flags, key, points, note):
    flags[key] = {"points": points, "note": note}


def main(data):
    missing = []
    flags = {}
    triggers = []
    ref = parse_time(data.get("reference_time"))
    card = data.get("card") if isinstance(data.get("card"), dict) else {}
    account = data.get("account") if isinstance(data.get("account"), dict) else {}
    home = data.get("home_location") if isinstance(data.get("home_location"), dict) else {}
    declines = data.get("declines") if isinstance(data.get("declines"), list) else None
    other_cards = data.get("other_cards") if isinstance(data.get("other_cards"), list) else None
    confirmations = data.get("confirmations") if isinstance(data.get("confirmations"), dict) else {}

    if not ref:
        missing.append("reference_time")
    if not all(norm(home.get(k)) for k in ("city", "state", "country")):
        missing.append("home_location.city/state/country")
    if declines is None or not declines:
        missing.append("declines")
        declines = []
    if other_cards is None:
        missing.append("other_cards")
        other_cards = []

    # Automatic escalation conditions.
    if norm(card.get("pin_lock_reason")) == "security_hold":
        triggers.append("security_hold_transfer_required")
    if any(bool(c.get("pin_locked")) for c in other_cards):
        triggers.append("other_pin_locked_cards_investigate_all_before_unlock")
    if ref:
        cutoff = ref - timedelta(days=90)
        for c in [card] + other_cards:
            issued = parse_date(c.get("date_issued"))
            if norm(c.get("issue_reason")) == "stolen" and issued and issued >= cutoff:
                triggers.append("recent_stolen_replacement_enhanced_verification_required")
                break

    # Validate decline fields before using them.
    valid_declines = []
    for d in declines:
        if not isinstance(d, dict):
            missing.append("valid declined transaction record")
            continue
        stamp = parse_time(d.get("timestamp"))
        try:
            amount = float(d.get("amount"))
        except (TypeError, ValueError):
            amount = None
        if not stamp or amount is None or not all(norm(d.get(k)) for k in ("city", "state", "country")):
            missing.append("decline timestamp/location/amount")
        else:
            item = dict(d)
            item["_time"] = stamp
            item["_amount"] = amount
            valid_declines.append(item)
    valid_declines.sort(key=lambda x: x["_time"])

    # A1 and A2.
    if valid_declines and "home_location.city/state/country" not in missing:
        mismatch_points = 0
        for d in valid_declines:
            if norm(d["country"]) != norm(home["country"]):
                mismatch_points = max(mismatch_points, 3)
            elif norm(d["state"]) != norm(home["state"]):
                mismatch_points = max(mismatch_points, 2)
            elif norm(d["city"]) != norm(home["city"]):
                mismatch_points = max(mismatch_points, 1)
        if confirmations.get("location_confirmed"):
            mismatch_points = 0
        add(flags, "A1_location_mismatch", mismatch_points, "location comparison completed")
        locations = {loc_key(d) for d in valid_declines}
        add(flags, "A2_location_scatter", 2 if len(locations) >= 3 else 1 if len(locations) == 2 else 0,
            "declined-attempt locations compared")
    else:
        missing.append("usable decline locations")

    # A3.
    success_locs = data.get("successful_last_7_locations")
    if not isinstance(success_locs, list):
        missing.append("successful_last_7_locations")
    elif valid_declines and all(isinstance(x, dict) and all(norm(x.get(k)) for k in ("city", "state", "country")) for x in success_locs):
        all_home = bool(success_locs) and all(same_location(x, home) for x in success_locs)
        declines_elsewhere = any(not same_location(d, home) for d in valid_declines)
        add(flags, "A3_travel_pattern_conflict", 1 if all_home and declines_elsewhere else 0,
            "recent successful-location pattern compared")
    else:
        missing.append("usable successful_last_7_locations")

    # B1 and B3 use the highest applicable observed risk.
    if valid_declines:
        time_points = 0
        for d in valid_declines:
            hour = d["_time"].hour + d["_time"].minute / 60
            pts = 3 if 2 <= hour < 6 else 2 if 0 <= hour < 2 else 1 if 22 <= hour < 24 else 0
            time_points = max(time_points, pts)
        if confirmations.get("time_confirmed"):
            time_points = 0
        add(flags, "B1_time_of_day", time_points, "decline times evaluated")
        gaps = [(b["_time"] - a["_time"]).total_seconds() / 60 for a, b in zip(valid_declines, valid_declines[1:])]
        min_gap = min(gaps) if gaps else None
        velocity = 3 if min_gap is not None and min_gap < 1 else 2 if min_gap is not None and min_gap < 2 else 1 if min_gap is not None and min_gap <= 5 else 0
        add(flags, "B3_attempt_velocity", velocity, "failed-attempt timing evaluated")
    else:
        missing.append("usable decline timestamps")

    pin_use = parse_time(data.get("successful_pin_use_at"))
    if not ref or not pin_use:
        missing.append("successful_pin_use_at")
    else:
        days = (ref - pin_use).total_seconds() / 86400
        add(flags, "B2_time_since_legitimate_pin_use", 2 if days > 30 else 1 if days >= 7 else 0,
            "last successful PIN use evaluated")

    # Amount flags.
    if valid_declines:
        amounts = [d["_amount"] for d in valid_declines]
        decreasing = len(amounts) >= 2 and all(b < a for a, b in zip(amounts, amounts[1:]))
        pattern = 2 if decreasing and not confirmations.get("amount_pattern_confirmed") else 0
        add(flags, "C1_amount_pattern", pattern, "ordered declined amounts evaluated")
        add(flags, "C2_round_number_testing", 1 if all(a > 0 and a % 100 == 0 for a in amounts) else 0,
            "round-number pattern evaluated")
        historical = data.get("successful_atm_amounts")
        if not isinstance(historical, list) or not historical:
            missing.append("successful_atm_amounts")
        else:
            try:
                average = sum(float(x) for x in historical) / len(historical)
                if average <= 0:
                    raise ValueError
                ratio = max(amounts) / average
                add(flags, "C3_amount_vs_historical_average", 2 if ratio > 5 else 1 if ratio > 2 else 0,
                    "attempted amount compared with successful ATM average")
            except (TypeError, ValueError):
                missing.append("numeric successful_atm_amounts")
        try:
            limit = float(card.get("daily_atm_limit"))
            if limit <= 0:
                raise ValueError
            total = sum(amounts)
            max_ratio = max(amounts) / limit
            daily_points = 2 if total > limit else 1 if .8 <= max_ratio <= 1 else 0
            add(flags, "C4_amount_vs_daily_limit", daily_points, "attempts compared with ATM limit")
        except (TypeError, ValueError):
            missing.append("card.daily_atm_limit")

    # Card and account-history flags.
    try:
        locks = int(card.get("prior_pin_locks_90d"))
        add(flags, "D1_lock_frequency", 3 if locks >= 3 else locks if locks in (1, 2) else 0, "prior lock count evaluated")
        if locks >= 3:
            triggers.append("three_or_more_prior_locks_pin_reset_required")
    except (TypeError, ValueError):
        missing.append("card.prior_pin_locks_90d")
    issued = parse_date(card.get("date_issued"))
    if not ref or not issued:
        missing.append("card.date_issued")
    else:
        age = (ref - issued).total_seconds() / 86400
        add(flags, "D2_card_age", 2 if age < 30 else 1 if age < 90 else 0, "card age evaluated")
    if other_cards is not None:
        other_points = 2 if any(bool(c.get("fraud_alert_active")) for c in other_cards) else 1 if any(bool(c.get("velocity_blocked")) for c in other_cards) else 0
        add(flags, "D3_other_card_issues", other_points, "other-card security indicators evaluated")
    opened = parse_date(account.get("opened_at"))
    if not ref or not opened:
        missing.append("account.opened_at")
    else:
        age = (ref - opened).total_seconds() / 86400
        add(flags, "E1_account_age", 2 if age < 90 else 1 if age < 180 else 0, "account age evaluated")
    try:
        overdrafts = int(account.get("overdraft_count"))
        add(flags, "E2_overdraft_history", 2 if overdrafts >= 2 else 1 if overdrafts == 1 else 0, "overdraft count evaluated")
    except (TypeError, ValueError):
        missing.append("account.overdraft_count")
    try:
        balance = float(account.get("current_balance"))
        add(flags, "E3_low_balance_alert", 2 if balance < 50 else 1 if balance < 100 else 0, "current balance band evaluated")
    except (TypeError, ValueError):
        missing.append("account.current_balance")

    missing = sorted(set(missing))
    score = sum(v["points"] for v in flags.values())
    single_three = [k for k, v in flags.items() if v["points"] == 3]
    if confirmations.get("customer_was_asleep"):
        triggers.append("customer_denied_time_attempt_asleep_critical_suspected_fraud")
    if missing:
        decision = "assessment_incomplete_do_not_unlock"
    elif any(t in triggers for t in ("security_hold_transfer_required", "customer_denied_time_attempt_asleep_critical_suspected_fraud")):
        decision = "do_not_unlock_transfer_security"
    elif "three_or_more_prior_locks_pin_reset_required" in triggers:
        decision = "do_not_unlock_pin_reset_required"
    elif single_three:
        decision = "supervisor_review_required_before_unlock"
    elif score >= 15:
        decision = "do_not_unlock_review_unauthorized_successes_and_security_options"
    elif score >= 11:
        decision = "do_not_unlock_callback_or_enhanced_verification_required"
    elif score >= 8:
        decision = "targeted_customer_confirmation_and_satisfactory_explanation_required"
    elif score >= 5:
        decision = "ask_whether_failed_attempts_were_customers_before_unlock"
    else:
        decision = "standard_identity_verification_required_before_eligible_unlock"
    print(json.dumps({"automatic_triggers": sorted(set(triggers)), "flags": flags,
                      "score": score if not missing else None, "single_three_point_flags": single_three,
                      "missing_inputs": missing, "decision": decision}, sort_keys=True))


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        main(payload)
    except Exception as exc:
        print(json.dumps({"error": "invalid_assessment_input", "detail": str(exc)}))
        sys.exit(2)
