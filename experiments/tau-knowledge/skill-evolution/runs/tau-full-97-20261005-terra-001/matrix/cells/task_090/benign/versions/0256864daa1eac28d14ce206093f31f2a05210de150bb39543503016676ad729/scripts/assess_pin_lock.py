#!/usr/bin/env python3
"""Deterministic decision aid for one PIN-locked debit card.

Input JSON:
{
  "now": "ISO-8601 datetime or MM/DD/YYYY",
  "customer_address": {"city": "...", "state": "...", "country": "..."},
  "card": {"card_id": "...", "pin_lock_reason": "...", "date_issued": "...",
           "daily_atm_limit": 0, "prior_pin_locks_90d": 0},
  "account": {"date_opened": "...", "balance": 0},
  "all_cards": [{"card_id": "...", "pin_locked": true, "issue_reason": "...",
                 "date_issued": "...", "velocity_blocked": false,
                 "fraud_alert_active": false}],
  "declined_attempts": [{"transaction_id": "...", "timestamp": "...", "amount": 0,
                         "city": "...", "state": "...", "country": "...",
                         "type": "atm_withdrawal_declined"}],
  "successful_transactions": [{"timestamp": "...", "amount": 0, "city": "...",
                               "type": "atm_withdrawal", "pin_used": true}],
  "transactions": [{"type": "overdraft_fee", "status": "posted", "amount": 0}],
  "confirmed_flags": ["A1", "A2", "A3", "B1", "C1"],
  "time_attempt_denied_as_asleep": false
}

Debit amounts may be negative. The output reports only calculable flags; unknown values
are never silently treated as zero. It emits JSON on stdout and uses no dependencies.
"""
import json
import sys
from datetime import datetime, timezone


def dt(value):
    if value is None or value == "":
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        out = datetime.fromisoformat(text)
        return out if out.tzinfo else out.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def n(value):
    return str(value or "").strip().casefold()


def money(value):
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return None


def age_days(now, then):
    return (now.date() - then.date()).days


def add(flags, code, points, detail):
    flags[code] = {"points": points, "detail": detail}


def main(data):
    now = dt(data.get("now"))
    if not now:
        raise ValueError("now is required and must be a supported date/datetime")
    card, account = data.get("card") or {}, data.get("account") or {}
    home = data.get("customer_address") or {}
    declines = data.get("declined_attempts") or []
    successful = data.get("successful_transactions") or []
    transactions, cards = data.get("transactions") or [], data.get("all_cards") or []
    flags, unknown, triggers = {}, [], []
    this_id = card.get("card_id")

    if n(card.get("pin_lock_reason")) == "security_hold":
        triggers.append("security_hold")
    other_locked = [x.get("card_id") for x in cards if x.get("pin_locked") and x.get("card_id") != this_id]
    if other_locked:
        triggers.append("other_cards_locked")
    stolen = []
    for item in cards:
        issued = dt(item.get("date_issued"))
        if n(item.get("issue_reason")) == "stolen" and issued and 0 <= age_days(now, issued) <= 90:
            stolen.append(item.get("card_id"))
    if stolen:
        triggers.append("recent_stolen_card_replacement")

    dated = [(dt(x.get("timestamp") or x.get("date")), x) for x in declines]
    if not declines:
        unknown.append("declined attempts needed for location, time, velocity, and amount flags")
    if declines and any(x[0] is None for x in dated):
        unknown.append("timestamps for all declined attempts")
    dated = [(when, item) for when, item in dated if when]

    # A1 and A2
    if declines and not n(home.get("city")):
        unknown.append("home city for A1")
    elif declines and any(not n(x.get("city")) for x in declines):
        unknown.append("declined-attempt cities for A1/A2")
    elif declines:
        highest = 0
        places = set()
        for item in declines:
            city, state, country = n(item.get("city")), n(item.get("state")), n(item.get("country"))
            places.add((city, state, country))
            if city == n(home.get("city")):
                p = 0
            elif country and n(home.get("country")) and country != n(home.get("country")):
                p = 3
            elif state and n(home.get("state")) and state != n(home.get("state")):
                p = 2
            else:
                p = 1
            highest = max(highest, p)
        add(flags, "A1", highest, "highest declined-attempt location mismatch")
        add(flags, "A2", 2 if len(places) >= 3 else 1 if len(places) == 2 else 0,
            "%d distinct declined locations" % len(places))

    # A3
    away = [x for x in declines if n(x.get("city")) and n(home.get("city")) and n(x.get("city")) != n(home.get("city"))]
    recent_success = []
    for item in successful:
        when = dt(item.get("timestamp") or item.get("date"))
        if when and 0 <= (now - when).total_seconds() <= 7 * 86400:
            recent_success.append(item)
    if away:
        if not recent_success or any(not n(x.get("city")) for x in recent_success):
            unknown.append("successful locations from prior 7 days for A3")
        else:
            all_home = all(n(x.get("city")) == n(home.get("city")) for x in recent_success)
            add(flags, "A3", 1 if all_home else 0, "recent successful activity location pattern")
    elif declines:
        add(flags, "A3", 0, "no established outside-home decline")

    # B1/B3
    if declines and len(dated) == len(declines):
        hours = [when.hour for when, _ in dated]
        risk = max(3 if 2 <= h < 6 else 2 if h < 2 else 1 if h >= 22 else 0 for h in hours)
        add(flags, "B1", risk, "highest declined-attempt time risk")
        if len(dated) >= 2:
            ordered = sorted(dated)
            gap = min((b[0] - a[0]).total_seconds() / 60 for a, b in zip(ordered, ordered[1:]))
            add(flags, "B3", 3 if gap < 1 else 2 if gap < 2 else 1 if gap <= 5 else 0,
                "shortest failed-attempt gap %.1f minutes" % gap)
        else:
            unknown.append("two dated declined attempts for B3")

    pin_uses = [dt(x.get("timestamp") or x.get("date")) for x in successful if x.get("pin_used") is True]
    pin_uses = [x for x in pin_uses if x]
    if not pin_uses:
        unknown.append("last successful PIN use for B2")
    else:
        days = age_days(now, max(pin_uses))
        add(flags, "B2", 2 if days > 30 else 1 if days >= 7 else 0, "last PIN use %d days ago" % days)

    amounts = [money(x.get("amount")) for x in declines]
    if declines and any(x is None for x in amounts):
        unknown.append("declined amounts for C1-C4")
    elif amounts:
        decreasing = len(amounts) >= 2 and all(a > b for a, b in zip(amounts, amounts[1:]))
        add(flags, "C1", 2 if decreasing else 0, "decreasing consecutive amounts" if decreasing else "not decreasing")
        hundreds = all(x > 0 and x % 100 == 0 for x in amounts)
        add(flags, "C2", 1 if hundreds else 0, "all amounts round hundreds" if hundreds else "mixed amounts")
        atm = [money(x.get("amount")) for x in successful if n(x.get("type")) == "atm_withdrawal"]
        atm = [x for x in atm if x is not None]
        if not atm:
            unknown.append("successful ATM withdrawals for C3")
        else:
            ratio = max(amounts) / (sum(atm) / len(atm))
            add(flags, "C3", 2 if ratio > 5 else 1 if ratio > 2 else 0, "largest attempt %.2fx ATM average" % ratio)
        limit = money(card.get("daily_atm_limit"))
        if not limit:
            unknown.append("daily ATM limit for C4")
        else:
            add(flags, "C4", 2 if sum(amounts) > limit else 1 if max(amounts) / limit >= .8 else 0,
                "attempt total compared with daily limit")

    locks = card.get("prior_pin_locks_90d")
    if locks is None:
        unknown.append("prior 90-day PIN-lock count for D1")
    else:
        locks = int(locks)
        add(flags, "D1", 3 if locks >= 3 else locks, "%d prior PIN locks" % locks)
    issued = dt(card.get("date_issued"))
    if not issued:
        unknown.append("card issuance date for D2")
    else:
        days = age_days(now, issued)
        add(flags, "D2", 2 if days < 30 else 1 if days < 90 else 0, "card age %d days" % days)
    others = [x for x in cards if x.get("card_id") != this_id]
    if not cards:
        unknown.append("other-card security status for D3")
    else:
        add(flags, "D3", 2 if any(x.get("fraud_alert_active") is True for x in others) else
            1 if any(x.get("velocity_blocked") is True for x in others) else 0, "other-card security state")
    opened = dt(account.get("date_opened"))
    if not opened:
        unknown.append("account opening date for E1")
    else:
        days = age_days(now, opened)
        add(flags, "E1", 2 if days < 90 else 1 if days < 180 else 0, "account age %d days" % days)
    if not transactions:
        unknown.append("transaction history for E2")
    else:
        fees = sum(1 for x in transactions if n(x.get("type")) == "overdraft_fee")
        add(flags, "E2", 2 if fees >= 2 else 1 if fees else 0, "%d overdraft fees" % fees)
    balance = money(account.get("balance"))
    if account.get("balance") is None:
        unknown.append("current balance for E3")
    else:
        add(flags, "E3", 2 if balance < 50 else 1 if balance < 100 else 0, "current balance")

    removable = {"A1", "A2", "A3", "B1", "C1"}
    for code in set(data.get("confirmed_flags") or []) & removable:
        if code in flags:
            flags[code]["removed_after_customer_confirmation"] = True
    score = sum(x["points"] for x in flags.values() if not x.get("removed_after_customer_confirmation"))
    three = [k for k, x in flags.items() if x["points"] == 3 and not x.get("removed_after_customer_confirmation")]
    disposition = ("standard_verification_then_unlock" if score <= 4 else
                   "ask_failed_attempt_ownership_then_unlock" if score <= 7 else
                   "ask_specific_location_and_time_then_unlock" if score <= 10 else
                   "callback_or_enhanced_verification_required" if score <= 14 else
                   "cannot_unlock_investigate_unauthorized_transactions")
    if locks is not None and locks >= 3:
        disposition = "pin_reset_required"
    if three:
        disposition = "supervisor_review_required"
    if data.get("time_attempt_denied_as_asleep"):
        triggers.append("customer_denied_high_risk_time_attempt")
        disposition = "security_team_required"
    if "security_hold" in triggers:
        disposition = "security_team_required"
    elif "other_cards_locked" in triggers:
        disposition = "investigate_all_locked_cards_before_any_unlock"

    return {"card_id": this_id, "automatic_triggers": triggers,
            "other_locked_card_ids": other_locked, "recent_stolen_card_ids": stolen,
            "flags": flags, "score": score, "three_point_flags": three,
            "unknown_inputs": sorted(set(unknown)), "disposition": disposition,
            "post_unlock_follow_up": "offer_pin_lock_notifications" if locks == 1 else
                                     "offer_pin_reset" if locks == 2 else "none"}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), indent=2, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
