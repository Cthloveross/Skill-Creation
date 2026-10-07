#!/usr/bin/env python3
"""Private deterministic PIN-lock risk scoring helper.

Input JSON schema (all timestamps ISO-8601; dates may be YYYY-MM-DD):
{
 "as_of": str,
 "home": {"city": str, "state": str, "country": str},
 "card": {"pin_lock_reason": str?, "date_issued": str?, "daily_atm_limit": number?,
          "prior_pin_locks_90": int?, "last_legitimate_pin_use": str?},
 "account": {"date_opened": str?, "balance": number?},
 "all_account_cards": [{"pin_locked": bool?, "issue_reason": str?, "date_issued": str?,
                        "velocity_blocked": bool?, "fraud_alert_active": bool?}],
 "declines": [{"timestamp": str, "city": str, "state": str, "country": str, "amount": number}],
 "successful_last_7d": [{"timestamp": str, "city": str, "state": str, "country": str}],
 "successful_atm_withdrawals": [{"timestamp": str, "amount": number}],
 "overdraft_fees": [{"date": str, "amount": number}]
}

Fields marked ? may be omitted and then appear in gaps. The output is internal-only.
"""
import json, sys
from datetime import datetime, date, timedelta


def dt(v):
    if not v: return None
    v = str(v).replace("Z", "+00:00")
    try: return datetime.fromisoformat(v)
    except ValueError:
        try: return datetime.combine(date.fromisoformat(v[:10]), datetime.min.time())
        except ValueError: return None

def day(v):
    x = dt(v)
    return x.date() if x else None

def norm(v): return str(v or "").strip().casefold()
def loc(x): return (norm(x.get("city")), norm(x.get("state")), norm(x.get("country")))
def age_days(now, value):
    x = day(value)
    return (now.date() - x).days if x else None

def main(data):
    now = dt(data.get("as_of"))
    if not now: raise ValueError("as_of must be ISO-8601")
    card, account = data.get("card") or {}, data.get("account") or {}
    home = data.get("home") or {}
    cards = data.get("all_account_cards")
    declines = data.get("declines")
    flags, gaps, triggers = {}, [], []
    def need(cond, label):
        if not cond: gaps.append(label)
    def put(key, points, evidence=None):
        flags[key] = {"points": points, "evidence": evidence}

    # Automatic trigger assessment
    if card.get("pin_lock_reason") == "security_hold": triggers.append("security_hold")
    need(isinstance(cards, list), "all_account_cards")
    if isinstance(cards, list):
        other_locked = any(c.get("pin_locked") is True for c in cards)
        # Caller should include only other cards or may mark target with is_target.
        if any(c.get("pin_locked") is True and not c.get("is_target", False) for c in cards):
            triggers.append("other_card_pin_locked")
        stolen = False
        for c in cards:
            if norm(c.get("issue_reason")) == "stolen":
                a = age_days(now, c.get("date_issued"))
                if a is not None and 0 <= a <= 90: stolen = True
        if stolen: triggers.append("recent_stolen_replacement")

    need(bool(home.get("city")) and bool(home.get("country")), "home location")
    need(isinstance(declines, list) and len(declines) > 0, "PIN decline records")
    valid_declines = []
    if isinstance(declines, list):
        for x in declines:
            if dt(x.get("timestamp")) and all(x.get(k) is not None for k in ("city","state","country","amount")):
                valid_declines.append(x)
        valid_declines.sort(key=lambda x: dt(x["timestamp"]))
        if declines and len(valid_declines) != len(declines): gaps.append("complete decline timestamp/location/amount fields")

    # A1/A2
    if valid_declines and home.get("city") and home.get("country"):
        vals=[]
        for x in valid_declines:
            if norm(x.get("country")) != norm(home.get("country")): p=3
            elif norm(x.get("state")) != norm(home.get("state")): p=2
            elif norm(x.get("city")) != norm(home.get("city")): p=1
            else: p=0
            vals.append(p)
        put("A1_location_mismatch", max(vals), {"worst": max(vals)})
        unique = {loc(x) for x in valid_declines}
        put("A2_location_scatter", 0 if len(unique)<=1 else 1 if len(unique)==2 else 2, {"locations":len(unique)})
    else:
        gaps.append("decline locations for A1/A2")

    successes = data.get("successful_last_7d")
    need(isinstance(successes, list), "successful transaction locations in last 7 days")
    if valid_declines and isinstance(successes, list) and home.get("city"):
        dated = [x for x in successes if dt(x.get("timestamp")) and (now-dt(x["timestamp"])) <= timedelta(days=7)]
        if dated and all(norm(x.get("city")) == norm(home.get("city")) for x in dated) and any(norm(x.get("city")) != norm(home.get("city")) for x in valid_declines):
            put("A3_travel_pattern_conflict", 1)
        else: put("A3_travel_pattern_conflict", 0)
    elif isinstance(successes, list):
        gaps.append("dated successful transaction locations for A3")

    if valid_declines:
        def hour_points(x):
            h=dt(x["timestamp"]).hour
            return 3 if 2<=h<6 else 2 if h<2 else 1 if h>=22 else 0
        put("B1_time_of_day", max(hour_points(x) for x in valid_declines))
        intervals=[(dt(b["timestamp"])-dt(a["timestamp"])).total_seconds()/60 for a,b in zip(valid_declines,valid_declines[1:])]
        p=0 if not intervals or min(intervals)>5 else 1 if min(intervals)>=2 else 2 if min(intervals)>=1 else 3
        put("B3_attempt_velocity", p, {"shortest_minutes": min(intervals) if intervals else None})
    else: gaps.append("decline timestamps for B1/B3")
    last = dt(card.get("last_legitimate_pin_use"))
    if last:
        days=(now-last).total_seconds()/86400
        put("B2_since_legitimate_pin_use", 0 if days<=7 else 1 if days<=30 else 2)
    else: gaps.append("last legitimate PIN use")

    if valid_declines:
        amounts=[abs(float(x["amount"])) for x in valid_declines]
        decreasing=len(amounts)>=3 and all(a>b for a,b in zip(amounts,amounts[1:]))
        put("C1_amount_pattern", 2 if decreasing else 0)
        put("C2_round_number_testing", 1 if amounts and all(a > 0 and a % 100 == 0 for a in amounts) else 0)
    else: gaps.append("decline amounts for C1/C2")
    atms=data.get("successful_atm_withdrawals")
    need(isinstance(atms, list), "successful ATM withdrawal history")
    if valid_declines and isinstance(atms, list):
        vals=[abs(float(x["amount"])) for x in atms if x.get("amount") is not None]
        if vals:
            avg=sum(vals)/len(vals); ratio=max(abs(float(x["amount"])) for x in valid_declines)/avg
            put("C3_amount_vs_historical_average", 0 if ratio<=2 else 1 if ratio<=5 else 2, {"average":avg})
        else: gaps.append("successful ATM amounts for C3")
    limit=card.get("daily_atm_limit")
    if valid_declines and limit is not None and float(limit)>0:
        total=sum(abs(float(x["amount"])) for x in valid_declines)
        maximum=max(abs(float(x["amount"])) for x in valid_declines)
        put("C4_amount_vs_daily_limit", 2 if total>float(limit) else 1 if maximum/float(limit)>=.8 else 0, {"total":total})
    else: gaps.append("card daily ATM limit")

    locks=card.get("prior_pin_locks_90")
    if locks is None: gaps.append("prior PIN locks in 90 days")
    else: put("D1_lock_frequency", 3 if int(locks)>=3 else int(locks))
    cd=age_days(now, card.get("date_issued"))
    if cd is None: gaps.append("card issue date")
    else: put("D2_card_age", 2 if cd<30 else 1 if cd<90 else 0)
    if isinstance(cards, list):
        other_fraud=any(c.get("fraud_alert_active") is True for c in cards)
        other_velocity=any(c.get("velocity_blocked") is True for c in cards)
        put("D3_other_card_issues", 2 if other_fraud else 1 if other_velocity else 0)
    ad=age_days(now, account.get("date_opened"))
    if ad is None: gaps.append("account opening date")
    else: put("E1_account_age", 2 if ad<90 else 1 if ad<180 else 0)
    fees=data.get("overdraft_fees")
    need(isinstance(fees, list), "overdraft fee history")
    if isinstance(fees, list): put("E2_overdraft_history", 2 if len(fees)>=2 else len(fees))
    bal=account.get("balance")
    if bal is None: gaps.append("current account balance")
    else:
        b=float(bal); put("E3_low_balance_alert", 2 if b<50 else 1 if b<100 else 0)

    total=sum(v["points"] for v in flags.values())
    max_flag=max((v["points"] for v in flags.values()), default=0)
    band="LOW" if total<=4 else "MEDIUM" if total<=7 else "HIGH" if total<=10 else "VERY_HIGH" if total<=14 else "CRITICAL"
    routing = "insufficient_evidence_no_unlock" if gaps else ("supervisor_review" if max_flag==3 else band.lower())
    if int(card.get("prior_pin_locks_90", 0) or 0)>=3: routing="pin_reset_required_no_unlock"
    if triggers: routing="automatic_escalation"
    return {"automatic_triggers":triggers,"flags":flags,"total_score":total,"risk_level":band,
            "single_three_point_flag":max_flag==3,"gaps":sorted(set(gaps)),"routing":routing}

if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except Exception as e:
        print(json.dumps({"error":str(e)}))
        sys.exit(1)
