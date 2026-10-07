#!/usr/bin/env python3
"""Fail-closed internal PIN-lock risk assessor. Reads JSON stdin, writes JSON stdout."""
import json, sys
from datetime import datetime, timezone


def dt(value):
    if not value:
        return None
    try:
        v = str(value).replace("Z", "+00:00")
        x = datetime.fromisoformat(v)
        return x.replace(tzinfo=x.tzinfo or timezone.utc)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(str(value), fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
    return None


def days_between(a, b):
    return (a - b).total_seconds() / 86400.0


def main(data):
    now = dt(data.get("now"))
    card, account = data.get("target_card") or {}, data.get("account") or {}
    declines = data.get("declines") or []
    missing, flags, notes = [], {}, []
    remove = set(data.get("remove_flags") or [])

    def add(code, points, reason):
        if code not in remove:
            flags[code] = {"points": points, "reason": reason}

    if not now: missing.append("now")
    if not card.get("card_id"): missing.append("target_card.card_id")
    if not declines: missing.append("declines")
    parsed = []
    for d in declines:
        t = dt(d.get("timestamp"))
        if not t or not all(d.get(k) is not None for k in ("city", "state", "country", "amount")):
            missing.append("complete declined attempt timestamp, location, and amount")
            continue
        parsed.append((t, d))
    parsed.sort(key=lambda x: x[0])

    # Automatic triggers are independent from the numerical score.
    cards = data.get("all_cards") or []
    security_hold = card.get("pin_lock_reason") == "security_hold"
    other_locked = any(c.get("pin_locked") and c.get("card_id") != card.get("card_id") for c in cards)
    recent_stolen = False
    if now:
        for c in cards:
            issued = dt(c.get("date_issued"))
            if c.get("issue_reason") == "stolen" and issued and 0 <= days_between(now, issued) <= 90:
                recent_stolen = True

    home = account.get("home_city")
    if parsed and home:
        loc_points = []
        foreign = []
        for _, d in parsed:
            if str(d["city"]).casefold() == str(home).casefold(): p = 0
            elif str(d["country"]).upper() != "US": p = 3
            elif d.get("state") == account.get("home_state"): p = 1
            else: p = 2
            loc_points.append(p)
        add("A1", max(loc_points), "declined-attempt location differs from home" if max(loc_points) else "same city")
        locations = {(str(d["city"]).casefold(), str(d["state"]).casefold(), str(d["country"]).casefold()) for _, d in parsed}
        add("A2", 2 if len(locations) >= 3 else 1 if len(locations) == 2 else 0, "distinct declined locations")
    else: missing.append("account.home_city/home_state and decline locations")

    success = data.get("successful_transactions_7d")
    if success is None: missing.append("successful_transactions_7d")
    elif parsed and home:
        ss = [x for x in success if dt(x.get("timestamp")) and days_between(now, dt(x["timestamp"])) <= 7]
        if ss:
            all_home = all(str(x.get("city", "")).casefold() == str(home).casefold() for x in ss)
            declines_elsewhere = any(str(d["city"]).casefold() != str(home).casefold() for _, d in parsed)
            add("A3", 1 if all_home and declines_elsewhere else 0, "recent successful-location pattern")
        else: missing.append("recent successful transaction locations")

    if parsed:
        hour_points = [0 if 6 <= t.hour < 22 else 1 if 22 <= t.hour or t.hour < 0 else 0 for t, _ in parsed]
        # Midnight ranges need explicit handling.
        hour_points = [0 if 6 <= t.hour < 22 else 1 if t.hour >= 22 else 2 if t.hour < 2 else 3 for t, _ in parsed]
        add("B1", max(hour_points), "highest-risk declined-attempt time")
        if len(parsed) >= 2:
            mins = [(parsed[i][0] - parsed[i-1][0]).total_seconds()/60 for i in range(1, len(parsed))]
            m = min(mins)
            add("B3", 3 if m < 1 else 2 if m < 2 else 1 if m <= 5 else 0, "closest consecutive failed-attempt interval")
        else: missing.append("at least two declined attempts for attempt velocity")
    pin_use = dt(data.get("last_legitimate_pin_use"))
    if now and pin_use:
        age = days_between(now, pin_use)
        add("B2", 2 if age > 30 else 1 if age >= 7 else 0, "time since legitimate PIN use")
    else: missing.append("last_legitimate_pin_use")

    amounts = [float(d["amount"]) for _, d in parsed] if parsed else []
    if amounts:
        decreasing = len(amounts) >= 3 and all(amounts[i] > amounts[i+1] for i in range(len(amounts)-1))
        add("C1", 2 if decreasing else 0, "consecutive decreasing attempts" if decreasing else "not a decreasing pattern")
        add("C2", 1 if all(a != 0 and abs(a) % 100 == 0 for a in amounts) else 0, "all amounts are round hundreds")
    averages = data.get("successful_atm_amounts")
    if averages is None or not averages: missing.append("successful_atm_amounts")
    elif amounts:
        avg = sum(map(float, averages)) / len(averages)
        ratio = max(abs(a) for a in amounts) / avg if avg else None
        if ratio is None: missing.append("nonzero historical ATM average")
        else: add("C3", 2 if ratio > 5 else 1 if ratio > 2 else 0, "attempt amount versus ATM average")
    limit = card.get("daily_atm_limit")
    if limit is None: missing.append("target_card.daily_atm_limit")
    elif amounts:
        total, limit = sum(abs(a) for a in amounts), float(limit)
        add("C4", 2 if total > limit else 1 if max(abs(a) for a in amounts) >= .8*limit else 0, "amount versus daily ATM limit")

    prior = data.get("prior_pin_locks_90d")
    if prior is None: missing.append("prior_pin_locks_90d")
    else: add("D1", 3 if prior >= 3 else int(prior), "PIN locks in prior 90 days")
    issued = dt(card.get("date_issued"))
    if now and issued:
        age = days_between(now, issued)
        add("D2", 2 if age < 30 else 1 if age < 90 else 0, "card age")
    else: missing.append("target_card.date_issued")
    other_issue = max((2 if c.get("fraud_alert_active") else 1 if c.get("velocity_blocked") else 0 for c in cards if c.get("card_id") != card.get("card_id")), default=0)
    add("D3", other_issue, "other-card security issue")
    opened = dt(account.get("opened"))
    if now and opened:
        age = days_between(now, opened)
        add("E1", 2 if age < 90 else 1 if age < 180 else 0, "account age")
    else: missing.append("account.opened")
    od, bal = data.get("overdraft_count"), account.get("balance")
    if od is None: missing.append("overdraft_count")
    else: add("E2", 2 if od >= 2 else 1 if od == 1 else 0, "recent overdraft count")
    if bal is None: missing.append("account.balance")
    else: add("E3", 2 if float(bal) < 50 else 1 if float(bal) < 100 else 0, "current balance")

    score = sum(x["points"] for x in flags.values())
    single_three = [k for k, v in flags.items() if v["points"] == 3]
    if security_hold: decision = "transfer_security_no_unlock"
    elif other_locked and not data.get("all_locked_investigated"): decision = "investigate_all_locked_cards_before_unlock"
    elif missing: decision = "investigate_before_decision"
    elif prior is not None and prior >= 3: decision = "pin_reset_required_no_unlock"
    elif single_three: decision = "supervisor_review_no_unlock"
    elif score >= 15: decision = "critical_no_unlock_review_unauthorized_transactions"
    elif score >= 11: decision = "no_unlock_callback_or_enhanced_verification"
    elif score >= 8: decision = "ask_location_time_and_require_satisfactory_explanation"
    elif score >= 5: decision = "ask_failed_attempt_ownership_question"
    else: decision = "eligible_for_standard_unlock_after_prerequisites"
    return {"automatic_triggers":{"security_hold":security_hold,"other_locked":other_locked,"recent_stolen_enhanced_verification":recent_stolen},"flags":flags,"score":score,"single_three_flags":single_three,"missing_inputs":sorted(set(missing)),"decision":decision,"customer_safe_summary":"A security review is required before any PIN-lock action; do not disclose internal scoring."}

if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"decision":"investigate_before_decision","error":"invalid assessment input: " + str(exc)}))
        sys.exit(1)
