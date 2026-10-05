#!/usr/bin/env python3
"""Assess one PIN-locked debit card according to the PIN Lock Investigation Protocol.

Input JSON (all date/datetime fields accept ISO-8601 or MM/DD/YYYY):
{
  "now": "ISO datetime or date",                         # required
  "customer_address": {"city": str, "state": str, "country": str},
  "card": {
    "card_id": str, "pin_lock_reason": str|null,
    "date_issued": date, "daily_atm_limit": number,
    "prior_pin_locks_90d": integer
  },
  "account": {"date_opened": date, "balance": number},
  "all_cards": [{"card_id": str, "pin_locked": bool,
                   "issue_reason": str, "date_issued": date,
                   "velocity_blocked": bool, "fraud_alert_active": bool}],
  "declined_attempts": [{"transaction_id": str, "timestamp": datetime,
      "amount": number, "city": str, "state": str, "country": str,
      "type": "atm_withdrawal_declined"|"pos_declined"}],
  "successful_transactions": [{"transaction_id": str, "timestamp": datetime,
      "amount": number, "city": str, "state": str, "country": str,
      "type": str, "pin_used": bool}],
  "transactions": [{"transaction_id": str, "date": date, "type": str,
                       "status": "posted"|"pending", "amount": number}],
  "confirmed_flags": ["A1", "A2", "A3", "B1", "C1"],
  "time_attempt_denied_as_asleep": false
}

Amounts may be negative as returned for debits; the calculation uses absolute values.
Output JSON contains flags, total score, unknown inputs, automatic triggers, questions,
and an initial disposition. Unknown data is never scored as zero.
"""
import json
import sys
from datetime import datetime, date, timezone

FLAG_NAMES = {
    "A1": "Location mismatch", "A2": "Location scatter", "A3": "Travel pattern conflict",
    "B1": "Time of day", "B2": "Time since last legitimate PIN use", "B3": "Attempt velocity",
    "C1": "Amount pattern", "C2": "Round-number testing", "C3": "Amount vs historical ATM average",
    "C4": "Amount vs daily ATM limit", "D1": "Lock frequency", "D2": "Card age",
    "D3": "Other card issues", "E1": "Account age", "E2": "Overdraft history", "E3": "Low balance alert",
}

def parse_dt(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(value).strip()
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            result = datetime.fromisoformat(candidate)
            return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None

def norm(value):
    return str(value or "").strip().casefold()

def amount(record):
    try:
        return abs(float(record.get("amount")))
    except (TypeError, ValueError):
        return None

def days_between(now, then):
    return (now.date() - then.date()).days

def add(flags, code, points, reason, evidence=None):
    flags[code] = {"name": FLAG_NAMES[code], "points": points, "reason": reason,
                   "evidence": evidence or []}

def location_key(t):
    parts = [norm(t.get(k)) for k in ("city", "state", "country")]
    return tuple(parts) if any(parts) else None

def is_home_location(t, home):
    return norm(t.get("city")) == norm(home.get("city")) and bool(norm(home.get("city")))

def main(data):
    now = parse_dt(data.get("now"))
    if not now:
        raise ValueError("now is required and must be a supported date or datetime")
    card = data.get("card") or {}
    account = data.get("account") or {}
    home = data.get("customer_address") or {}
    declines = data.get("declined_attempts") or []
    successes = data.get("successful_transactions") or []
    transactions = data.get("transactions") or []
    all_cards = data.get("all_cards") or []
    confirmed = set(data.get("confirmed_flags") or [])
    flags, unknown, triggers = {}, [], []

    # Automatic triggers
    if norm(card.get("pin_lock_reason")) == "security_hold":
        triggers.append("security_hold")
    this_id = card.get("card_id")
    other_locked = [c.get("card_id") for c in all_cards if c.get("pin_locked") and c.get("card_id") != this_id]
    if other_locked:
        triggers.append("other_cards_locked")
    recent_stolen = []
    for c in all_cards:
        issued = parse_dt(c.get("date_issued"))
        if norm(c.get("issue_reason")) == "stolen" and issued and 0 <= days_between(now, issued) <= 90:
            recent_stolen.append(c.get("card_id"))
    if recent_stolen:
        triggers.append("recent_stolen_card_replacement")

    dated_declines = [(parse_dt(t.get("timestamp") or t.get("date")), t) for t in declines]
    if declines and any(d is None for d, _ in dated_declines):
        unknown.append("timestamps for one or more declined attempts")
    dated_declines = [(d, t) for d, t in dated_declines if d]

    # A1 highest mismatch severity among reported decline locations.
    if not declines:
        unknown.append("declined PIN attempts needed for location, time, velocity, and amount flags")
    elif not norm(home.get("city")):
        unknown.append("customer address city needed for A1/A3")
    elif any(not norm(t.get("city")) for t in declines):
        unknown.append("declined-attempt city needed for A1")
    else:
        highest, evidence = 0, []
        for t in declines:
            if norm(t.get("city")) == norm(home.get("city")):
                p = 0
            elif norm(t.get("country")) and norm(home.get("country")) and norm(t.get("country")) != norm(home.get("country")):
                p = 3
            elif norm(t.get("state")) and norm(home.get("state")) and norm(t.get("state")) != norm(home.get("state")):
                p = 2
            else:
                p = 1
            if p > highest:
                highest = p
                evidence = [t.get("transaction_id")] if t.get("transaction_id") else []
        add(flags, "A1", highest, "highest declined-attempt location mismatch", evidence)

    locations = [location_key(t) for t in declines]
    if declines and any(x is None for x in locations):
        unknown.append("complete locations needed for A2")
    elif declines:
        n = len(set(locations))
        add(flags, "A2", 2 if n >= 3 else 1 if n == 2 else 0, f"{n} distinct declined-attempt location(s)")

    seven_days = [t for d, t in [(parse_dt(x.get("timestamp") or x.get("date")), x) for x in successes]
                  if d and 0 <= (now - d).total_seconds() <= 7 * 86400]
    declines_elsewhere = bool(declines and norm(home.get("city")) and any(not is_home_location(t, home) for t in declines if norm(t.get("city"))))
    if declines_elsewhere:
        if not seven_days or any(not norm(t.get("city")) for t in seven_days):
            unknown.append("successful transaction locations from last 7 days needed for A3")
        elif all(is_home_location(t, home) for t in seven_days):
            add(flags, "A3", 1, "all successful activity in prior 7 days is in home city while declines are elsewhere")
        else:
            add(flags, "A3", 0, "recent successful activity indicates travel")
    elif declines:
        add(flags, "A3", 0, "no declined attempt established as outside home city")

    if declines and len(dated_declines) == len(declines):
        highest, evidence = 0, []
        for d, t in dated_declines:
            hour = d.hour
            p = 3 if 2 <= hour < 6 else 2 if 0 <= hour < 2 else 1 if hour >= 22 else 0
            if p > highest:
                highest, evidence = p, [t.get("transaction_id")] if t.get("transaction_id") else []
        add(flags, "B1", highest, "highest-risk declined-attempt hour", evidence)
    elif declines:
        unknown.append("declined-attempt timestamps needed for B1")

    pin_successes = []
    for t in successes:
        if t.get("pin_used") is True:
            d = parse_dt(t.get("timestamp") or t.get("date"))
            if d: pin_successes.append(d)
    if not pin_successes:
        unknown.append("last successful PIN use needed for B2")
    else:
        age = days_between(now, max(pin_successes))
        p = 2 if age > 30 else 1 if age >= 7 else 0
        add(flags, "B2", p, f"last successful PIN use {age} day(s) ago")

    if len(dated_declines) < 2:
        unknown.append("at least two dated declined attempts needed for B3")
    elif len(dated_declines) == len(declines):
        ordered = sorted(dated_declines, key=lambda x: x[0])
        mins = min((b[0] - a[0]).total_seconds() / 60 for a, b in zip(ordered, ordered[1:]))
        p = 3 if mins < 1 else 2 if mins < 2 else 1 if mins <= 5 else 0
        add(flags, "B3", p, f"shortest gap between consecutive failures: {mins:.1f} minute(s)")

    amounts = [amount(t) for t in declines]
    if declines and any(a is None for a in amounts):
        unknown.append("declined-attempt amounts needed for C1/C2/C3/C4")
    elif amounts:
        decreasing = len(amounts) >= 2 and all(a > b for a, b in zip(amounts, amounts[1:]))
        add(flags, "C1", 2 if decreasing else 0, "strictly decreasing consecutive attempt amounts" if decreasing else "not a decreasing consecutive amount pattern")
        all_hundreds = all(a > 0 and abs(a / 100 - round(a / 100)) < 1e-9 for a in amounts)
        add(flags, "C2", 1 if all_hundreds else 0, "all attempted amounts are round hundreds" if all_hundreds else "attempt amounts are mixed or non-hundreds")
        atm_success_amounts = [amount(t) for t in successes if norm(t.get("type")) == "atm_withdrawal" and amount(t) is not None]
        if not atm_success_amounts:
            unknown.append("recent successful ATM withdrawals needed for C3")
        else:
            avg = sum(atm_success_amounts) / len(atm_success_amounts)
            ratio = max(amounts) / avg if avg else None
            p = 2 if ratio and ratio > 5 else 1 if ratio and ratio > 2 else 0
            add(flags, "C3", p, f"largest attempt is {ratio:.2f}x successful ATM average" if ratio else "ATM average is zero")
        limit = amount({"amount": card.get("daily_atm_limit")})
        if not limit:
            unknown.append("daily ATM limit needed for C4")
        else:
            total, maximum = sum(amounts), max(amounts)
            p = 2 if total > limit else 1 if maximum / limit >= .8 else 0
            add(flags, "C4", p, "attempt total exceeds daily ATM limit" if total > limit else "largest attempt compared with daily ATM limit")

    locks = card.get("prior_pin_locks_90d")
    if locks is None:
        unknown.append("prior PIN-lock count in last 90 days needed for D1")
    else:
        locks = int(locks)
        add(flags, "D1", 3 if locks >= 3 else locks, f"{locks} prior PIN lock(s) in 90 days")
    issued = parse_dt(card.get("date_issued"))
    if not issued:
        unknown.append("card issuance date needed for D2")
    else:
        age = days_between(now, issued)
        add(flags, "D2", 2 if age < 30 else 1 if age < 90 else 0, f"card active about {age} day(s)")
    other = [c for c in all_cards if c.get("card_id") != this_id]
    if not all_cards:
        unknown.append("other-card security status needed for D3")
    elif any(c.get("fraud_alert_active") is True for c in other):
        add(flags, "D3", 2, "another card has active fraud alert")
    elif any(c.get("velocity_blocked") is True for c in other):
        add(flags, "D3", 1, "another card has velocity block")
    else:
        add(flags, "D3", 0, "no other-card security issue reported")

    opened = parse_dt(account.get("date_opened"))
    if not opened:
        unknown.append("account opening date needed for E1")
    else:
        age = days_between(now, opened)
        add(flags, "E1", 2 if age < 90 else 1 if age < 180 else 0, f"account open about {age} day(s)")
    overdrafts = [t for t in transactions if norm(t.get("type")) == "overdraft_fee"]
    if transactions:
        add(flags, "E2", 2 if len(overdrafts) >= 2 else 1 if len(overdrafts) == 1 else 0, f"{len(overdrafts)} overdraft fee(s) in supplied history")
    else:
        unknown.append("transaction history needed for E2")
    balance = amount({"amount": account.get("balance")})
    if account.get("balance") is None:
        unknown.append("current account balance needed for E3")
    else:
        add(flags, "E3", 2 if balance < 50 else 1 if balance < 100 else 0, f"current balance ${balance:.2f}")

    # Confirmation only clears the three flags explicitly allowed by protocol.
    removable = {"A1", "A2", "A3", "B1", "C1"}
    for code in confirmed & removable:
        if code in flags:
            flags[code]["removed_after_customer_confirmation"] = True
    total = sum(v["points"] for k, v in flags.items() if not v.get("removed_after_customer_confirmation"))
    three_point = [k for k, v in flags.items() if v["points"] == 3 and not v.get("removed_after_customer_confirmation")]

    questions = []
    if total >= 5:
        if flags.get("A1", {}).get("points", 0) and not flags["A1"].get("removed_after_customer_confirmation"):
            questions.append("Ask whether the customer was at each declined-attempt location shown in the source records.")
        if flags.get("C1", {}).get("points", 0) and not flags["C1"].get("removed_after_customer_confirmation"):
            questions.append("Ask whether the customer remembers trying the specific declined amounts, in their recorded order.")
        if flags.get("B1", {}).get("points", 0) >= 2 and not flags["B1"].get("removed_after_customer_confirmation"):
            questions.append("Ask whether the customer was attempting to use the card at the recorded time.")
    if total >= 8:
        questions.append("Ask specific location and time questions and require confirmation plus a satisfactory explanation before any unlock.")

    disposition = "standard_verification_then_unlock" if total <= 4 else "ask_failed-attempt-ownership_then_unlock" if total <= 7 else "ask_specific_location_and_time_then_unlock" if total <= 10 else "callback_or_enhanced_verification_required" if total <= 14 else "cannot_unlock_investigate_unauthorized_transactions"
    if locks is not None and locks >= 3:
        disposition = "pin_reset_required"
    if three_point:
        disposition = "supervisor_review_required"
    if data.get("time_attempt_denied_as_asleep"):
        disposition = "security_team_required"
        triggers.append("customer_denied_high-risk-time_attempt")
    if "security_hold" in triggers:
        disposition = "security_team_required"
    elif "other_cards_locked" in triggers:
        disposition = "investigate_all_locked_cards_before_any_unlock"

    return {"card_id": this_id, "automatic_triggers": triggers, "recent_stolen_card_ids": recent_stolen,
            "other_locked_card_ids": other_locked, "flags": flags, "score": total,
            "three_point_flags": three_point, "unknown_inputs": sorted(set(unknown)),
            "required_customer_questions": questions, "disposition": disposition,
            "post_unlock_follow_up": "offer_pin_lock_notifications" if locks == 1 else "offer_pin_reset" if locks == 2 else "none"}

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), indent=2, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
