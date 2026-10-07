#!/usr/bin/env python3
"""Internal deterministic PIN-lock risk scorer.
Reads one JSON object from stdin and writes one JSON result to stdout.
Unknown evidence is reported in `missing` and is never silently scored as zero.
"""
import json
import sys
from datetime import datetime, timezone


def parse_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = datetime.strptime(text, "%m/%d/%Y")
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def norm(value):
    return str(value or "").strip().casefold()


def loc_key(loc):
    loc = loc or {}
    return (norm(loc.get("city")), norm(loc.get("state")), norm(loc.get("country")))


def location_complete(loc):
    city, state, country = loc_key(loc)
    return bool(city and state and country)


def add(flags, name, points, note):
    flags[name] = {"points": points, "note": note}


def main(data):
    missing = []
    flags = {}
    now = parse_date(data.get("now"))
    home = data.get("home")
    raw_declines = data.get("declines")
    if now is None:
        missing.append("now")
    if not location_complete(home):
        missing.append("home location (city, state, country)")
    if not isinstance(raw_declines, list) or not raw_declines:
        missing.append("declined ATM/POS PIN attempts")
        declines = []
    else:
        declines = list(raw_declines)

    parsed_declines = []
    for i, item in enumerate(declines):
        stamp = parse_date(item.get("timestamp"))
        amount = item.get("amount")
        if stamp is None:
            missing.append("decline[%d] timestamp" % i)
        if not location_complete(item.get("location")):
            missing.append("decline[%d] resolved location" % i)
        try:
            amount = abs(float(amount))
        except (TypeError, ValueError):
            missing.append("decline[%d] amount" % i)
            amount = None
        parsed_declines.append((stamp, amount, item.get("location") or {}))
    parsed_declines.sort(key=lambda x: x[0] or datetime.min.replace(tzinfo=timezone.utc))

    # A1 and A2
    if parsed_declines and location_complete(home) and all(location_complete(x[2]) for x in parsed_declines):
        hc, hs, hcountry = loc_key(home)
        mismatch = 0
        for _, _, place in parsed_declines:
            c, s, country = loc_key(place)
            if country != hcountry:
                mismatch = max(mismatch, 3)
            elif s != hs:
                mismatch = max(mismatch, 2)
            elif c != hc:
                mismatch = max(mismatch, 1)
        add(flags, "A1_location_mismatch", mismatch, "highest mismatch among declined attempts")
        unique = {loc_key(x[2]) for x in parsed_declines}
        add(flags, "A2_location_scatter", 2 if len(unique) >= 3 else 1 if len(unique) == 2 else 0,
            "%d distinct declined locations" % len(unique))
    else:
        missing.append("complete locations for A1/A2")

    # A3
    successes = data.get("successful_transactions_last_7_days")
    if not isinstance(successes, list):
        missing.append("successful transactions from last 7 days")
    elif location_complete(home) and any(not location_complete(x.get("location")) for x in successes):
        missing.append("resolved locations for successful transactions")
    elif parsed_declines and location_complete(home) and all(location_complete(x[2]) for x in parsed_declines):
        home_key = loc_key(home)
        all_success_home = bool(successes) and all(loc_key(x.get("location")) == home_key for x in successes)
        declines_elsewhere = any(loc_key(x[2]) != home_key for x in parsed_declines)
        add(flags, "A3_travel_pattern_conflict", 1 if all_success_home and declines_elsewhere else 0,
            "successful activity confined to home city" if all_success_home else "recent travel/mixed or no successful activity")

    # B1
    if parsed_declines and all(x[0] is not None for x in parsed_declines):
        def hour_points(hour):
            if 2 <= hour < 6: return 3
            if 0 <= hour < 2: return 2
            if 22 <= hour < 24: return 1
            return 0
        b1 = max(hour_points(x[0].hour) for x in parsed_declines)
        add(flags, "B1_time_of_day", b1, "highest-risk declined-attempt time")
    else:
        missing.append("decline timestamps for B1")

    # B2
    pin_use = parse_date(data.get("last_legitimate_pin_use"))
    if now is None or pin_use is None:
        missing.append("last legitimate PIN use")
    else:
        days = max(0, (now - pin_use).total_seconds() / 86400)
        pts = 2 if days > 30 else 1 if days >= 7 else 0
        add(flags, "B2_time_since_legitimate_pin_use", pts, "%.1f days since PIN use" % days)

    # B3
    if len(parsed_declines) < 2:
        missing.append("at least two decline timestamps for B3")
    elif any(x[0] is None for x in parsed_declines):
        missing.append("complete decline timestamps for B3")
    else:
        gaps = [(parsed_declines[i][0] - parsed_declines[i-1][0]).total_seconds() / 60 for i in range(1, len(parsed_declines))]
        gap = min(gaps)
        pts = 3 if gap < 1 else 2 if gap < 2 else 1 if gap <= 5 else 0
        add(flags, "B3_attempt_velocity", pts, "minimum gap %.1f minutes" % gap)

    amounts = [x[1] for x in parsed_declines]
    if amounts and all(x is not None for x in amounts):
        decreasing = len(amounts) >= 2 and all(amounts[i] < amounts[i-1] for i in range(1, len(amounts)))
        add(flags, "C1_amount_pattern", 2 if decreasing else 0,
            "strictly decreasing attempts" if decreasing else "not a decreasing attempt sequence")
        all_round = all(a > 0 and abs(a / 100 - round(a / 100)) < 1e-9 for a in amounts)
        add(flags, "C2_round_number_testing", 1 if all_round else 0,
            "all amounts are round hundreds" if all_round else "amounts are mixed/non-round")
    else:
        missing.append("complete decline amounts for C1/C2")

    successful_atm = data.get("successful_atm_amounts")
    if not isinstance(successful_atm, list) or not successful_atm:
        missing.append("recent successful ATM withdrawal amounts for C3")
    elif not amounts or any(x is None for x in amounts):
        missing.append("decline amounts for C3")
    else:
        try:
            avg = sum(abs(float(x)) for x in successful_atm) / len(successful_atm)
            if avg <= 0: raise ValueError
            ratio = max(amounts) / avg
            add(flags, "C3_amount_vs_historical_average", 2 if ratio > 5 else 1 if ratio > 2 else 0,
                "largest attempt is %.2fx historical ATM average" % ratio)
        except (TypeError, ValueError):
            missing.append("valid positive successful ATM withdrawal amounts for C3")

    limit = data.get("daily_atm_limit")
    if not amounts or any(x is None for x in amounts):
        missing.append("decline amounts for C4")
    else:
        try:
            limit = float(limit)
            if limit <= 0: raise ValueError
            total = sum(amounts)
            largest_ratio = max(amounts) / limit
            pts = 2 if total > limit else 1 if largest_ratio >= .8 else 0
            add(flags, "C4_amount_vs_daily_limit", pts,
                "attempt total %.2f; largest is %.0f%% of limit" % (total, largest_ratio * 100))
        except (TypeError, ValueError):
            missing.append("positive daily ATM limit for C4")

    prior = data.get("prior_locks_90d")
    try:
        prior = int(prior)
        if prior < 0: raise ValueError
        add(flags, "D1_lock_frequency", 3 if prior >= 3 else prior, "%d prior locks in 90 days" % prior)
    except (TypeError, ValueError):
        missing.append("prior PIN-lock count in last 90 days")

    issued = parse_date(data.get("card_active_since"))
    if now is None or issued is None:
        missing.append("card active/issue date")
    else:
        days = max(0, (now - issued).total_seconds() / 86400)
        add(flags, "D2_card_age", 2 if days < 30 else 1 if days < 90 else 0, "%.1f days active" % days)

    others = data.get("other_cards")
    if not isinstance(others, list):
        missing.append("other-card security flags")
    else:
        fraud = any(bool(x.get("fraud_alert")) for x in others)
        velocity = any(bool(x.get("velocity_block")) for x in others)
        add(flags, "D3_other_card_issues", 2 if fraud else 1 if velocity else 0,
            "fraud alert" if fraud else "velocity block" if velocity else "no reported issue")

    opened = parse_date(data.get("account_opened"))
    if now is None or opened is None:
        missing.append("account opening date")
    else:
        days = max(0, (now - opened).total_seconds() / 86400)
        add(flags, "E1_account_age", 2 if days < 90 else 1 if days < 180 else 0, "%.1f days open" % days)

    overdrafts = data.get("overdraft_fee_count")
    try:
        overdrafts = int(overdrafts)
        if overdrafts < 0: raise ValueError
        add(flags, "E2_overdraft_history", 2 if overdrafts >= 2 else 1 if overdrafts == 1 else 0,
            "%d overdraft fees" % overdrafts)
    except (TypeError, ValueError):
        missing.append("recent overdraft fee count")

    balance = data.get("current_balance")
    try:
        balance = float(balance)
        add(flags, "E3_low_balance_alert", 2 if balance < 50 else 1 if balance < 100 else 0,
            "current balance supplied")
    except (TypeError, ValueError):
        missing.append("current account balance")

    total = sum(item["points"] for item in flags.values())
    level = "INCOMPLETE" if missing else ("LOW" if total <= 4 else "MEDIUM" if total <= 7 else "HIGH" if total <= 10 else "VERY_HIGH" if total <= 14 else "CRITICAL")
    three_point = [name for name, item in flags.items() if item["points"] == 3]
    gates = []
    if missing:
        gates.append("Do not make an unlock decision until missing material evidence is resolved.")
    if three_point:
        gates.append("Supervisor review required because at least one flag is three points.")
    if isinstance(prior, int) and prior >= 3:
        gates.append("Cannot unlock: three or more prior locks require PIN reset.")
    if not missing:
        if total >= 15: gates.append("Cannot unlock; investigate unauthorized successful transactions and consider closure/replacement.")
        elif total >= 11: gates.append("Cannot unlock in this interaction; require callback or enhanced verification.")
        elif total >= 8: gates.append("Ask location/time questions indicated by flags; unlock only with confirmed satisfactory explanation.")
        elif total >= 5: gates.append("Ask whether failed PIN attempts were the customer's before any unlock.")
        else: gates.append("Standard identity verification is still required before any unlock.")
    return {"flags": flags, "total": total, "risk_level": level,
            "single_flag_escalation": bool(three_point), "three_point_flags": three_point,
            "missing": sorted(set(missing)), "decision_gates": gates}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
