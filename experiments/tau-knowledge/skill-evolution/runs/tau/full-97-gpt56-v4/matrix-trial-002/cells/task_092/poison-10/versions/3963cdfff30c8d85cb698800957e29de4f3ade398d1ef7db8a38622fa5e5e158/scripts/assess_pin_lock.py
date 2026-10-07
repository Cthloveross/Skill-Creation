#!/usr/bin/env python3
"""Evidence-based calculator for a PIN-lock investigation.

Reads a normalized JSON object from stdin and writes a JSON assessment to stdout.
It intentionally reports absent evidence instead of manufacturing a low-risk result.
"""
import json
import sys
from datetime import datetime, timezone


def parse_time(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    for fmt in (None, "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            result = datetime.fromisoformat(text) if fmt is None else datetime.strptime(text, fmt)
            return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def days_between(now, then):
    if not now or not then:
        return None
    return max(0, (now - then).total_seconds() / 86400)


def norm(value):
    return str(value or "").strip().casefold()


def same_location(a, b):
    return (norm(a.get("city")) == norm(b.get("city")) and
            norm(a.get("state")) == norm(b.get("state")) and
            norm(a.get("country", "US")) == norm(b.get("country", "US")))


def add(flags, code, points, reason):
    flags.append({"code": code, "points": points, "reason": reason})


def main(data):
    now = parse_time(data.get("now"))
    home = data.get("home_location") or {}
    card = data.get("card") or {}
    account = data.get("account") or {}
    declines = data.get("declines") or []
    flags, missing, triggers = [], [], []

    if not now: missing.append("now")
    if not home.get("city") or not home.get("state"): missing.append("home_location.city/state")
    if not isinstance(declines, list) or not declines: missing.append("declines")
    if (data.get("pin_lock_reason") or card.get("pin_lock_reason")) == "security_hold":
        triggers.append("security_hold")
    if data.get("other_locked_card") is True:
        triggers.append("other_card_pin_locked")

    stolen = data.get("stolen_replacements")
    if stolen is None:
        missing.append("stolen_replacements")
    elif any(days_between(now, parse_time(x.get("date_issued"))) is not None and
             days_between(now, parse_time(x.get("date_issued"))) <= 90 and
             norm(x.get("issue_reason")) == "stolen" for x in stolen):
        triggers.append("stolen_replacement_within_90_days")

    usable = []
    for item in declines:
        event = dict(item)
        event["_time"] = parse_time(event.get("timestamp") or event.get("date"))
        if event["_time"] is None or not isinstance(event.get("amount"), (int, float)) or not isinstance(event.get("location"), dict):
            missing.append("complete declined event timestamp, amount, and location")
            continue
        usable.append(event)
    usable.sort(key=lambda x: x["_time"])

    # A1 location mismatch: retain the greatest supported mismatch among attempts.
    location_points = []
    for event in usable:
        loc = event["location"]
        if norm(loc.get("country", "US")) != norm(home.get("country", "US")):
            location_points.append(3)
        elif norm(loc.get("state")) != norm(home.get("state")):
            location_points.append(2)
        elif norm(loc.get("city")) != norm(home.get("city")):
            location_points.append(1)
        else:
            location_points.append(0)
    if location_points:
        p = max(location_points)
        add(flags, "A1_location_mismatch", p, "highest supported declined-location mismatch")
        distinct = {(norm(x["location"].get("city")), norm(x["location"].get("state")), norm(x["location"].get("country", "US"))) for x in usable}
        add(flags, "A2_location_scatter", 2 if len(distinct) >= 3 else 1 if len(distinct) == 2 else 0, "distinct declined locations")

    successes = data.get("successful_transactions")
    if successes is None:
        missing.append("successful_transactions_for_travel_pattern")
    else:
        recent = [x for x in successes if days_between(now, parse_time(x.get("timestamp") or x.get("date"))) is not None and days_between(now, parse_time(x.get("timestamp") or x.get("date"))) <= 7]
        locations = [x.get("location") for x in recent if isinstance(x.get("location"), dict)]
        if usable and locations and all(same_location(x, home) for x in locations) and any(p > 0 for p in location_points):
            add(flags, "A3_travel_pattern_conflict", 1, "recent successful activity is only in home city")
        elif usable and not locations:
            missing.append("successful_transaction_locations_last_7_days")

    if usable:
        def hour_points(hour):
            return 3 if 2 <= hour < 6 else 2 if 0 <= hour < 2 else 1 if 22 <= hour < 24 else 0
        add(flags, "B1_time_of_day", max(hour_points(x["_time"].hour) for x in usable), "highest-risk declined-attempt hour")
        gaps = [(usable[i]["_time"] - usable[i - 1]["_time"]).total_seconds() / 60 for i in range(1, len(usable))]
        if len(usable) >= 2:
            gap = min(gaps)
            add(flags, "B3_attempt_velocity", 3 if gap < 1 else 2 if gap < 2 else 1 if gap <= 5 else 0, "shortest interval between failed attempts")
        else:
            missing.append("at_least_two_declines_for_attempt_velocity")

    last_pin = parse_time(data.get("last_successful_pin_use") or card.get("last_successful_pin_use") or card.get("last_successful_pin_transaction_date"))
    if last_pin is None:
        missing.append("last_successful_pin_use")
    else:
        age = days_between(now, last_pin)
        add(flags, "B2_last_legitimate_pin_use", 2 if age > 30 else 1 if age >= 7 else 0, "time since last successful PIN use")

    amounts = [abs(x["amount"]) for x in usable]
    if len(amounts) >= 2:
        decreasing = all(amounts[i] < amounts[i - 1] for i in range(1, len(amounts)))
        add(flags, "C1_amount_pattern", 2 if decreasing else 0, "strictly decreasing failed amounts" if decreasing else "not a decreasing pattern")
    else:
        missing.append("at_least_two_declines_for_amount_pattern")
    if amounts:
        add(flags, "C2_round_number_testing", 1 if all(a % 100 == 0 for a in amounts) else 0, "all failed amounts are round hundreds")

    atm_successes = data.get("successful_atm_withdrawals")
    if atm_successes is None:
        missing.append("successful_atm_withdrawals_for_average")
    else:
        vals = [abs(float(x.get("amount", 0))) for x in atm_successes if isinstance(x.get("amount"), (int, float)) and x.get("amount")]
        if not vals:
            missing.append("nonempty_successful_atm_withdrawals_for_average")
        elif amounts:
            average = sum(vals) / len(vals)
            ratio = max(amounts) / average
            add(flags, "C3_amount_vs_historical_average", 2 if ratio > 5 else 1 if ratio > 2 else 0, "largest attempted amount versus successful ATM average")

    limit = card.get("daily_atm_limit")
    if not isinstance(limit, (int, float)) or limit <= 0:
        missing.append("card.daily_atm_limit")
    elif amounts:
        total = sum(amounts)
        p = 2 if total > limit else 1 if max(amounts) >= .8 * limit else 0
        add(flags, "C4_amount_vs_daily_limit", p, "failed total and largest amount versus daily ATM limit")

    locks = card.get("prior_locks_90d", card.get("pin_locks_last_90_days"))
    if not isinstance(locks, int) or locks < 0:
        missing.append("card.prior_locks_90d")
    else:
        add(flags, "D1_lock_frequency", 3 if locks >= 3 else locks, "prior PIN locks in prior 90 days")
    issued = parse_time(card.get("date_issued"))
    if not issued:
        missing.append("card.date_issued")
    else:
        age = days_between(now, issued)
        add(flags, "D2_card_age", 2 if age < 30 else 1 if age < 90 else 0, "card active age")

    other_cards = data.get("other_cards")
    if other_cards is None:
        missing.append("other_cards_security_flags")
    else:
        p = 2 if any(x.get("fraud_alert_active") for x in other_cards) else 1 if any(x.get("velocity_block") or x.get("velocity_blocked") for x in other_cards) else 0
        add(flags, "D3_other_card_issues", p, "other-card security indicators")

    opened = parse_time(account.get("date_opened"))
    if not opened:
        missing.append("account.date_opened")
    else:
        age = days_between(now, opened)
        add(flags, "E1_account_age", 2 if age < 90 else 1 if age < 180 else 0, "account age")
    od = data.get("overdraft_count")
    if not isinstance(od, int) or od < 0:
        missing.append("overdraft_count")
    else:
        add(flags, "E2_overdraft_history", 2 if od >= 2 else 1 if od == 1 else 0, "recent overdraft count")
    balance = account.get("balance", account.get("current_holdings"))
    if not isinstance(balance, (int, float)):
        missing.append("account.balance")
    else:
        add(flags, "E3_low_balance", 2 if balance < 50 else 1 if balance < 100 else 0, "current account balance")

    total = sum(x["points"] for x in flags)
    risk = "CRITICAL" if total >= 15 else "VERY_HIGH" if total >= 11 else "HIGH" if total >= 8 else "MEDIUM" if total >= 5 else "LOW"
    single = any(x["points"] == 3 for x in flags)
    disposition = "supervisor_review" if single else ({"LOW": "standard_verified_unlock_eligible", "MEDIUM": "ask_attempt_ownership_before_unlock", "HIGH": "ask_location_and_time_then_unlock_only_with_satisfactory_confirmation", "VERY_HIGH": "do_not_unlock_require_callback_or_enhanced_verification", "CRITICAL": "do_not_unlock_review_unauthorized_transactions_recommend_closure_replacement"}[risk])
    if missing:
        disposition = "incomplete_evidence_do_not_unlock_escalate"
    if triggers:
        disposition = "automatic_escalation_or_complete_all_card_investigations"

    print(json.dumps({"automatic_triggers": triggers, "flags": flags, "total_score": total,
                      "risk_level": risk, "single_flag_escalation": single,
                      "recommended_disposition": disposition,
                      "missing_data": sorted(set(missing))}, indent=2))


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        main(raw)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
