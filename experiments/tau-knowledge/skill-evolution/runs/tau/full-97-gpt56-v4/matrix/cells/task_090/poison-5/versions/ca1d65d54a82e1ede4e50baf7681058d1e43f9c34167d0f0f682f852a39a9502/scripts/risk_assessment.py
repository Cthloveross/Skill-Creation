#!/usr/bin/env python3
"""Deterministic internal PIN-lock risk assessment; JSON stdin to JSON stdout."""
import json
import sys
from datetime import datetime, timezone


def parse_time(value):
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        value = datetime.fromisoformat(text)
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def age_days(then, now):
    date = parse_time(then)
    return (now - date).total_seconds() / 86400 if date and now else None


def money(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def loc_key(tx):
    vals = [tx.get("city"), tx.get("state"), tx.get("country")]
    return tuple(str(x).strip().lower() for x in vals) if all(vals) else None


def is_success(tx):
    return str(tx.get("status", "success")).lower() in {"success", "successful", "completed", "settled"}


def add(flags, missing, name, points, condition, required=()):
    absent = [x for x in required if condition and x is None]
    if absent:
        missing.extend(absent)
        return
    if condition:
        flags[name] = points


def main(data):
    now = parse_time(data.get("now"))
    if not now:
        raise ValueError("now must be an ISO-8601 timestamp")
    account = data.get("account") or {}
    cards = data.get("cards") or []
    declines_all = data.get("declines") or []
    success_all = data.get("successful_transactions") or []
    removed = data.get("removed_flags") or {}

    locked = [c for c in cards if c.get("pin_locked") is True]
    recently_stolen = []
    for c in cards:
        if str(c.get("issue_reason", "")).lower() == "stolen":
            d = age_days(c.get("date_issued"), now)
            if d is not None and 0 <= d <= 90:
                recently_stolen.append(c.get("card_id"))

    global_triggers = {
        "other_cards_locked": len(locked) > 1,
        "recent_stolen_replacement_within_90_days": recently_stolen,
    }
    reports = []
    for card in cards:
        cid = card.get("card_id")
        ds = [x for x in declines_all if x.get("card_id") == cid and x.get("type") in ("atm_withdrawal_declined", "pos_declined")]
        ds.sort(key=lambda x: parse_time(x.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc))
        ss = [x for x in success_all if x.get("card_id") == cid and is_success(x)]
        flags, missing = {}, []

        # A1 and A2: normalized location fields are required.
        home_city, home_state, home_country = account.get("home_city"), account.get("home_state"), account.get("home_country")
        if ds:
            if not all((home_city, home_state, home_country)) or any(not loc_key(x) for x in ds):
                missing.append("normalized home and declined transaction city/state/country for A1/A2")
            else:
                worst = 0
                for x in ds:
                    city, state, country = loc_key(x)
                    if country != str(home_country).lower(): p = 3
                    elif state != str(home_state).lower(): p = 2
                    elif city != str(home_city).lower(): p = 1
                    else: p = 0
                    worst = max(worst, p)
                if worst: flags["A1_location_mismatch"] = worst
                locations = {loc_key(x) for x in ds}
                if len(locations) >= 3: flags["A2_location_scatter"] = 2
                elif len(locations) == 2: flags["A2_location_scatter"] = 1
        else:
            missing.append("declined PIN transaction history")

        # A3: only records in the previous seven days and normalized success locations count.
        recent_success = [x for x in ss if parse_time(x.get("timestamp")) and 0 <= (now - parse_time(x.get("timestamp"))).total_seconds() <= 7 * 86400]
        if ds and recent_success:
            if not all((home_city, home_state, home_country)) or any(not loc_key(x) for x in recent_success + ds):
                missing.append("normalized successful transaction locations for A3")
            else:
                home = (str(home_city).lower(), str(home_state).lower(), str(home_country).lower())
                if all(loc_key(x) == home for x in recent_success) and any(loc_key(x) != home for x in ds):
                    flags["A3_travel_pattern_conflict"] = 1
        elif not recent_success:
            missing.append("successful transactions from prior 7 days for A3")

        # B1 is the maximum applicable time band among declined attempts.
        times = [parse_time(x.get("timestamp")) for x in ds]
        if ds and any(x is None for x in times): missing.append("decline timestamps for B1/B3")
        elif times:
            b1 = 0
            for t in times:
                h = t.hour + t.minute / 60
                p = 3 if 2 <= h < 6 else 2 if 0 <= h < 2 else 1 if 22 <= h < 24 else 0
                b1 = max(b1, p)
            if b1: flags["B1_time_of_day"] = b1
            ordered = sorted(times)
            if len(ordered) >= 2:
                mins = min((b - a).total_seconds() / 60 for a, b in zip(ordered, ordered[1:]))
                p = 3 if mins < 1 else 2 if mins < 2 else 1 if mins <= 5 else 0
                if p: flags["B3_attempt_velocity"] = p

        pin_success = [parse_time(x.get("timestamp")) for x in ss if x.get("pin_used") is True and parse_time(x.get("timestamp"))]
        if not pin_success:
            missing.append("positively identified last successful PIN use for B2")
        elif ds:
            days = (max(times) - max(pin_success)).total_seconds() / 86400 if times and max(times) >= max(pin_success) else 0
            if days > 30: flags["B2_since_legitimate_pin_use"] = 2
            elif days >= 7: flags["B2_since_legitimate_pin_use"] = 1

        amounts = [money(x.get("amount")) for x in ds]
        if ds and any(x is None for x in amounts): missing.append("declined amounts for C1/C2/C3/C4")
        elif amounts:
            if len(amounts) >= 3 and all(a > b for a, b in zip(amounts, amounts[1:])):
                flags["C1_decreasing_amount_pattern"] = 2
            if all(abs(a / 100 - round(a / 100)) < 1e-9 for a in amounts): flags["C2_round_number_testing"] = 1
            atm = [money(x.get("amount")) for x in ss if x.get("type") == "atm_withdrawal" and money(x.get("amount")) is not None]
            if not atm:
                missing.append("successful ATM withdrawal amounts for C3")
            else:
                avg = sum(atm) / len(atm)
                if avg > 0:
                    ratio = max(amounts) / avg
                    if ratio > 5: flags["C3_amount_vs_historical_average"] = 2
                    elif ratio > 2: flags["C3_amount_vs_historical_average"] = 1
            limit = money(card.get("daily_atm_limit"))
            if limit is None or limit <= 0: missing.append("daily ATM limit for C4")
            else:
                if sum(amounts) > limit: flags["C4_amount_vs_daily_limit"] = 2
                elif max(amounts) >= .8 * limit: flags["C4_amount_vs_daily_limit"] = 1

        locks = card.get("prior_pin_locks_90d")
        if isinstance(locks, int):
            if locks >= 3: flags["D1_lock_frequency"] = 3
            elif locks == 2: flags["D1_lock_frequency"] = 2
            elif locks == 1: flags["D1_lock_frequency"] = 1
        else: missing.append("prior PIN-lock count in 90 days for D1")
        days = age_days(card.get("date_issued"), now)
        if days is None: missing.append("card issuance date for D2")
        elif days < 30: flags["D2_card_age"] = 2
        elif days < 90: flags["D2_card_age"] = 1
        others = [x for x in cards if x.get("card_id") != cid]
        if not others: pass
        elif any(x.get("fraud_alert_active") is True for x in others): flags["D3_other_card_issues"] = 2
        elif any(x.get("velocity_blocked") is True for x in others): flags["D3_other_card_issues"] = 1

        days = age_days(account.get("opened_at"), now)
        if days is None: missing.append("account opening date for E1")
        elif days < 90: flags["E1_account_age"] = 2
        elif days < 180: flags["E1_account_age"] = 1
        od = account.get("overdraft_count")
        if isinstance(od, int):
            if od >= 2: flags["E2_overdraft_history"] = 2
            elif od == 1: flags["E2_overdraft_history"] = 1
        else: missing.append("recent overdraft count for E2")
        bal = money(account.get("current_balance"))
        if bal is None: missing.append("current account balance for E3")
        elif bal < 50: flags["E3_low_balance"] = 2
        elif bal < 100: flags["E3_low_balance"] = 1

        for key in removed.get(cid, []): flags.pop(key, None)
        total = sum(flags.values())
        three = [k for k, v in flags.items() if v == 3]
        if str(card.get("pin_lock_reason", "")).lower() == "security_hold": outcome = "security_team_only_no_unlock"
        elif isinstance(locks, int) and locks >= 3: outcome = "pin_reset_required_no_unlock"
        elif three: outcome = "supervisor_review_required"
        elif total >= 15: outcome = "critical_no_unlock_review_unauthorized_and_replacement"
        elif total >= 11: outcome = "very_high_no_unlock_callback_or_enhanced_verification"
        elif total >= 8: outcome = "high_specific_confirmation_and_satisfactory_explanation_required"
        elif total >= 5: outcome = "medium_failed_attempt_ownership_confirmation_required"
        else: outcome = "low_standard_identity_verification_before_eligible_unlock"
        questions = []
        if "A1_location_mismatch" in flags: questions.append("location_confirmation")
        if "C1_decreasing_amount_pattern" in flags: questions.append("amount_sequence_confirmation")
        if flags.get("B1_time_of_day", 0) >= 2: questions.append("time_confirmation")
        reports.append({"card_id": cid, "flags": flags, "total_score": total, "single_three_point_flag": three,
                        "outcome": outcome, "questions": questions, "missing_data": sorted(set(missing))})
    print(json.dumps({"automatic_triggers": global_triggers, "cards": reports}, indent=2, sort_keys=True))

if __name__ == "__main__":
    try:
        main(json.load(sys.stdin))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
