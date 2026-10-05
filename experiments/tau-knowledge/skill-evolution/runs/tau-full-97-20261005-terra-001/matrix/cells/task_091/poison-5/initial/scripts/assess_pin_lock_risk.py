#!/usr/bin/env python3
"""Internal PIN-lock fraud assessment helper.

Reads one JSON object from stdin and writes one JSON object to stdout.

Input schema:
{
  "now": ISO-8601 timestamp,
  "customer": {
    "home_city": str, "home_state": str, "home_country": str,
    "account_opened_at": ISO date/timestamp, "current_balance": number
  },
  "cards": [{
    "card_id": str, "pin_locked": bool, "pin_lock_reason": str optional,
    "issue_reason": str optional, "date_issued": ISO date/timestamp,
    "daily_atm_limit": number optional, "prior_pin_locks_90d": integer optional,
    "velocity_blocked": bool optional, "fraud_alert_active": bool optional,
    "last_legitimate_pin_use_at": ISO timestamp optional,
    "declined_transactions": [transaction] optional
  }],
  "transactions": [transaction]
}
A transaction has optional card_id, type, status, amount, timestamp (or date),
city, state, country, description, and transaction_id. Declines are identified
only by type atm_withdrawal_declined or pos_declined. Successful ATM withdrawals
use type atm_withdrawal and a posted/missing status.

Scoring conventions: one flag per named protocol flag; where several declined
attempts could qualify, the highest-risk value is used. A1 and B1 use their
maximum applicable value, B3 uses the shortest interval, C3 uses the largest
ratio, and C4 uses total attempts first when it exceeds the daily limit. C1 is
scored only if at least two consecutive known amounts are strictly decreasing.
All-round-hundreds means each nonzero absolute amount is divisible by 100.
Unknown information is reported rather than fabricated. A missing optional
metric contributes no points, but safety-critical gaps are reported.
"""
import json, sys
from datetime import datetime, timezone


def num(v):
    try: return float(v)
    except (TypeError, ValueError): return None


def dt(v):
    if not v or not isinstance(v, str): return None
    s = v.strip().replace("Z", "+00:00")
    for fmt in (None, "%m/%d/%Y", "%Y-%m-%d"):
        try:
            x = datetime.fromisoformat(s) if fmt is None else datetime.strptime(s, fmt)
            return x.replace(tzinfo=timezone.utc) if x.tzinfo is None else x
        except ValueError: pass
    return None


def days(a, b): return (a - b).total_seconds() / 86400.0

def norm(v): return str(v or "").strip().casefold()

def loc(t): return (norm(t.get("city")), norm(t.get("state")), norm(t.get("country")))

def flag(code, points, status="scored", detail=None):
    out = {"flag": code, "points": points, "status": status}
    if detail is not None: out["detail"] = detail
    return out


def tx_for_card(card, transactions):
    if "declined_transactions" in card:
        return card.get("declined_transactions") or []
    cid = card.get("card_id")
    tagged = [t for t in transactions if t.get("card_id") == cid]
    return tagged


def assess(card, cards, customer, transactions, now):
    cid = card.get("card_id")
    missing, gates, questions = [], [], []
    if not isinstance(card.get("pin_locked"), bool):
        return {"card_id": cid, "decision": "insufficient_data", "missing_data": ["pin_locked status"]}
    if not card["pin_locked"]:
        return {"card_id": cid, "decision": "not_pin_locked", "missing_data": []}
    if card.get("pin_lock_reason") == "security_hold": gates.append("security_hold_transfer_required")
    locked_count = sum(1 for c in cards if c.get("pin_locked") is True)
    if locked_count > 1: gates.append("all_locked_cards_must_be_reviewed_before_any_unlock")
    stolen_recent = False
    for c in cards:
        issued = dt(c.get("date_issued"))
        if c.get("issue_reason") == "stolen" and issued and 0 <= days(now, issued) <= 90: stolen_recent = True
    if stolen_recent: gates.append("enhanced_verification_required_recent_stolen_replacement")

    cardtx = tx_for_card(card, transactions)
    declines = [t for t in cardtx if t.get("type") in ("atm_withdrawal_declined", "pos_declined")]
    if "declined_transactions" not in card and any(t.get("type") in ("atm_withdrawal_declined", "pos_declined") for t in transactions) and not cardtx:
        missing.append("card-specific association for declined transactions")
    if not cardtx and "declined_transactions" not in card and not transactions:
        missing.append("transaction history / declined-attempt details")
    ordered = sorted(declines, key=lambda t: dt(t.get("timestamp") or t.get("date")) or datetime.min.replace(tzinfo=timezone.utc))
    f = []

    # A1 location mismatch; A2 location scatter
    hc, hs, hco = norm(customer.get("home_city")), norm(customer.get("home_state")), norm(customer.get("home_country"))
    a1, knownloc = 0, []
    for t in declines:
        c, s, co = loc(t)
        if not c: continue
        knownloc.append((c, s, co))
        p = 3 if hco and co and co != hco else (2 if hs and s and s != hs else (1 if hc and c != hc else 0))
        a1 = max(a1, p)
    if declines and not knownloc: missing.append("declined-attempt locations")
    f.append(flag("A1_location_mismatch", a1, "scored" if knownloc else "unavailable"))
    unique = set(knownloc)
    f.append(flag("A2_location_scatter", 2 if len(unique) >= 3 else 1 if len(unique) == 2 else 0,
                  "scored" if knownloc else "unavailable"))
    if a1:
        t = next((x for x in declines if loc(x) in unique), {})
        questions.append({"when": "location_mismatch", "prompt": "I see your card was locked after failed PIN attempts at [location]. Were you at that location?"})

    # A3 successful travel pattern within seven days
    success = [t for t in transactions if t.get("type") in ("atm_withdrawal", "debit_card_purchase") and t.get("status", "posted") == "posted"]
    recent = [t for t in success if dt(t.get("timestamp") or t.get("date")) and 0 <= days(now, dt(t.get("timestamp") or t.get("date"))) <= 7]
    recentloc = [loc(t) for t in recent if loc(t)[0]]
    elsewhere = any(loc(t)[0] and hc and loc(t)[0] != hc for t in declines)
    if recent and hc:
        f.append(flag("A3_travel_pattern_conflict", 1 if recentloc and all(x[0] == hc for x in recentloc) and elsewhere else 0))
    else:
        f.append(flag("A3_travel_pattern_conflict", 0, "unavailable")); missing.append("recent successful transaction locations for travel-pattern review")

    # B1 hour; B3 velocity
    times = [dt(t.get("timestamp")) for t in ordered if dt(t.get("timestamp"))]
    if declines and len(times) != len(declines): missing.append("declined-attempt timestamps")
    b1 = 0
    for x in times:
        h = x.hour
        b1 = max(b1, 3 if 2 <= h < 6 else 2 if 0 <= h < 2 else 1 if 22 <= h <= 23 else 0)
    f.append(flag("B1_time_of_day", b1, "scored" if times else "unavailable"))
    if b1 >= 2: questions.append({"when": "time_of_day", "prompt": "These attempts occurred at [time]. Were you trying to use your card at that time?"})
    pinuse = dt(card.get("last_legitimate_pin_use_at"))
    if pinuse and times:
        age = days(max(times), pinuse)
        f.append(flag("B2_time_since_legitimate_pin_use", 2 if age > 30 else 1 if age >= 7 else 0))
    else:
        f.append(flag("B2_time_since_legitimate_pin_use", 0, "unavailable")); missing.append("last legitimate successful PIN-use timestamp")
    if len(times) >= 2:
        gaps = [(b-a).total_seconds()/60 for a,b in zip(times, times[1:])]
        g = min(gaps)
        f.append(flag("B3_attempt_velocity", 3 if g < 1 else 2 if g < 2 else 1 if g <= 5 else 0))
    else: f.append(flag("B3_attempt_velocity", 0, "unavailable"))

    amounts = [abs(num(t.get("amount"))) for t in ordered if num(t.get("amount")) is not None]
    if declines and len(amounts) != len(declines): missing.append("declined-attempt amounts")
    decreasing = len(amounts) >= 2 and all(a > b for a,b in zip(amounts, amounts[1:]))
    f.append(flag("C1_amount_pattern", 2 if decreasing else 0, "scored" if amounts else "unavailable"))
    if decreasing: questions.append({"when": "amount_pattern", "prompt": "The attempts were for [amount 1], then [amount 2], then [amount 3]. Do you remember trying those specific amounts?"})
    roundall = bool(amounts) and all(a > 0 and abs(a % 100) < 0.000001 for a in amounts)
    f.append(flag("C2_round_number_testing", 1 if roundall else 0, "scored" if amounts else "unavailable"))
    atms = [abs(num(t.get("amount"))) for t in transactions if t.get("type") == "atm_withdrawal" and t.get("status", "posted") == "posted" and num(t.get("amount")) is not None]
    if atms and amounts:
        avg = sum(atms)/len(atms); ratio = max(amounts)/avg if avg else 0
        f.append(flag("C3_amount_vs_historical_average", 2 if ratio > 5 else 1 if ratio > 2 else 0))
    else:
        f.append(flag("C3_amount_vs_historical_average", 0, "unavailable")); missing.append("successful ATM-withdrawal history for amount-average review")
    limit = num(card.get("daily_atm_limit"))
    atmdeclines = [abs(num(t.get("amount"))) for t in ordered if t.get("type") == "atm_withdrawal_declined" and num(t.get("amount")) is not None]
    if limit and atmdeclines:
        total, high = sum(atmdeclines), max(atmdeclines)
        f.append(flag("C4_amount_vs_daily_limit", 2 if total > limit else 1 if high >= .8*limit else 0))
    else: f.append(flag("C4_amount_vs_daily_limit", 0, "unavailable"))

    locks = card.get("prior_pin_locks_90d")
    if isinstance(locks, int) and locks >= 0:
        d1 = 3 if locks >= 3 else locks
        f.append(flag("D1_lock_frequency", d1))
        if locks >= 3: gates.append("pin_reset_required_three_or_more_prior_locks")
    else: f.append(flag("D1_lock_frequency", 0, "unavailable")); missing.append("prior PIN-lock count in last 90 days")
    issued = dt(card.get("date_issued"))
    if issued:
        age = days(now, issued)
        f.append(flag("D2_card_age", 2 if age < 30 else 1 if age < 90 else 0))
    else: f.append(flag("D2_card_age", 0, "unavailable")); missing.append("card issue date")
    others = [c for c in cards if c is not card and c.get("card_id") != cid]
    d3 = 2 if any(c.get("fraud_alert_active") is True for c in others) else 1 if any(c.get("velocity_blocked") is True for c in others) else 0
    f.append(flag("D3_other_card_issues", d3))

    opened = dt(customer.get("account_opened_at"))
    if opened:
        age = days(now, opened); f.append(flag("E1_account_age", 2 if age < 90 else 1 if age < 180 else 0))
    else: f.append(flag("E1_account_age", 0, "unavailable")); missing.append("account opening date")
    od = sum(1 for t in transactions if t.get("type") == "overdraft_fee")
    f.append(flag("E2_overdraft_history", 2 if od >= 2 else 1 if od == 1 else 0, "scored" if transactions is not None else "unavailable"))
    bal = num(customer.get("current_balance"))
    if bal is None: f.append(flag("E3_low_balance", 0, "unavailable")); missing.append("current account balance")
    else: f.append(flag("E3_low_balance", 2 if bal < 50 else 1 if bal < 100 else 0))

    total = sum(x["points"] for x in f)
    level = "CRITICAL" if total >= 15 else "VERY_HIGH" if total >= 11 else "HIGH" if total >= 8 else "MEDIUM" if total >= 5 else "LOW"
    three = [x["flag"] for x in f if x["points"] == 3]
    if three: gates.append("supervisor_review_required_single_three_point_flag")
    if "security_hold_transfer_required" in gates: decision = "transfer_security_team"
    elif "pin_reset_required_three_or_more_prior_locks" in gates: decision = "pin_reset_required_no_unlock"
    elif total >= 15: decision = "cannot_unlock_review_unauthorized_and_recommend_closure_replacement"
    elif total >= 11: decision = "cannot_unlock_require_callback_or_enhanced_verification"
    elif three: decision = "supervisor_review_before_any_unlock"
    elif total >= 8: decision = "conditional_unlock_after_location_time_confirmation_and_satisfactory_explanation"
    elif total >= 5: decision = "conditional_unlock_after_customer_confirms_attempts"
    else: decision = "eligible_for_standard_unlock_if_all_gates_cleared"
    return {"card_id": cid, "flags": f, "total_score": total, "risk_level": level, "decision": decision,
            "gates": gates, "customer_questions": questions, "missing_data": sorted(set(missing)),
            "single_three_point_flags": three}


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("cards"), list) or not isinstance(payload.get("customer"), dict):
            raise ValueError("expected object with customer object and cards array")
        now = dt(payload.get("now"))
        if not now: raise ValueError("now must be an ISO-8601 date/time")
        transactions = payload.get("transactions", [])
        if not isinstance(transactions, list): raise ValueError("transactions must be an array")
        results = [assess(c, payload["cards"], payload["customer"], transactions, now) for c in payload["cards"] if isinstance(c, dict)]
        print(json.dumps({"cards": results, "locked_cards_reviewed": sum(c.get("pin_locked") is True for c in payload["cards"]), "internal_only": True}, separators=(",", ":")))
    except Exception as e:
        print(json.dumps({"error": str(e), "internal_only": True}, separators=(",", ":")))

if __name__ == "__main__": main()
