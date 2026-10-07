#!/usr/bin/env python3
"""Deterministic PIN-lock fraud assessment. Reads one JSON object from stdin, writes JSON."""
import json, sys
from datetime import datetime, timezone


def parse_dt(value):
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def age_days(now, value):
    dt = parse_dt(value)
    return None if not dt else (now - dt).total_seconds() / 86400


def loc_key(x):
    return tuple(str(x.get(k, "")).strip().casefold() for k in ("city", "state", "country"))


def add(flags, code, points, reason, removed):
    flags[code] = {"points": 0 if code in removed else points,
                   "raw_points": points, "removed": code in removed, "reason": reason}


def main(data):
    missing = []
    now = parse_dt(data.get("now"))
    if not now:
        return {"error": "now must be an ISO-8601 timestamp"}
    removed = set(data.get("removed_flags") or [])
    card, account = data.get("card") or {}, data.get("account") or {}
    declines = data.get("declines") or []
    declines = [x for x in declines if x.get("type") in ("atm_withdrawal_declined", "pos_declined")]
    declines.sort(key=lambda x: parse_dt(x.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc))
    flags = {}
    home = data.get("home") or {}

    # A1 uses the most severe declined-attempt mismatch.
    if not declines or not all(home.get(k) for k in ("city", "state", "country")) or not all(all(d.get(k) for k in ("city", "state", "country")) for d in declines):
        missing.append("home and complete declined locations for A1")
    else:
        hp = loc_key(home); scores = []
        for d in declines:
            p = 0 if loc_key(d) == hp else (1 if str(d['state']).casefold() == hp[1] else (2 if str(d['country']).casefold() == hp[2] else 3))
            scores.append(p)
        add(flags, "A1", max(scores), "most severe declined-attempt location mismatch", removed)
    if not declines or not all(all(d.get(k) for k in ("city", "state", "country")) for d in declines):
        missing.append("complete declined locations for A2")
    else:
        n = len({loc_key(d) for d in declines}); add(flags, "A2", 0 if n <= 1 else 1 if n == 2 else 2, f"{n} distinct declined locations", removed)
    successes7 = data.get("successful_transactions_7d")
    if successes7 is None or not declines or not home.get("city"):
        missing.append("7-day successful locations and home city for A3")
    else:
        all_home = all(str(x.get("city", "")).casefold() == str(home["city"]).casefold() for x in successes7)
        decline_elsewhere = any(str(x.get("city", "")).casefold() != str(home["city"]).casefold() for x in declines)
        add(flags, "A3", 1 if successes7 and all_home and decline_elsewhere else 0, "home-only success pattern versus declines", removed)

    times = [parse_dt(d.get("timestamp")) for d in declines]
    if not declines or any(x is None for x in times): missing.append("declined timestamps for B1/B3")
    else:
        def hour_score(t):
            h = t.hour + t.minute / 60
            return 3 if 2 <= h < 6 else 2 if 0 <= h < 2 else 1 if 22 <= h < 24 else 0
        add(flags, "B1", max(hour_score(t) for t in times), "highest-risk declined time of day", removed)
        gaps = [(times[i] - times[i-1]).total_seconds()/60 for i in range(1, len(times))]
        p = 0 if not gaps else (3 if min(gaps) < 1 else 2 if min(gaps) < 2 else 1 if min(gaps) <= 5 else 0)
        add(flags, "B3", p, "shortest consecutive failed-attempt interval", removed)
    pins = data.get("successful_pin_uses")
    if pins is None: missing.append("successful PIN-use timestamps for B2")
    else:
        valid = [parse_dt(x.get("timestamp")) for x in pins]; valid = [x for x in valid if x]
        if not valid: missing.append("a valid last successful PIN-use timestamp for B2")
        else:
            days = (now - max(valid)).total_seconds()/86400
            add(flags, "B2", 2 if days > 30 else 1 if days >= 7 else 0, "time since last successful PIN use", removed)

    amounts = [d.get("amount") for d in declines]
    if not declines or any(not isinstance(a, (int, float)) or a < 0 for a in amounts): missing.append("non-negative declined amounts for C1/C2/C4")
    else:
        add(flags, "C1", 2 if len(amounts) >= 2 and all(amounts[i] < amounts[i-1] for i in range(1, len(amounts))) else 0, "strictly decreasing consecutive attempts", removed)
        add(flags, "C2", 1 if amounts and all(a > 0 and a % 100 == 0 for a in amounts) else 0, "all attempted amounts are round hundreds", removed)
        limit = card.get("daily_atm_limit")
        if not isinstance(limit, (int, float)) or limit <= 0: missing.append("positive daily ATM limit for C4")
        else:
            total = sum(amounts); maxratio = max(amounts)/limit
            add(flags, "C4", 2 if total > limit else 1 if maxratio >= .8 else 0, "attempts versus daily ATM limit", removed)
    atms = data.get("successful_atm_withdrawals")
    if atms is None: missing.append("successful ATM withdrawals for C3")
    else:
        hist = [x.get("amount") for x in atms if isinstance(x.get("amount"), (int,float)) and x.get("amount") >= 0]
        if not hist or not amounts or any(not isinstance(a,(int,float)) for a in amounts): missing.append("valid successful ATM and declined amounts for C3")
        else:
            avg = sum(hist)/len(hist)
            if avg <= 0: missing.append("nonzero historical ATM average for C3")
            else:
                ratio = max(amounts)/avg; add(flags, "C3", 2 if ratio > 5 else 1 if ratio > 2 else 0, "largest attempt versus historical ATM average", removed)

    locks = card.get("prior_pin_locks_90d")
    if not isinstance(locks, int) or locks < 0: missing.append("prior PIN-lock count for D1")
    else: add(flags, "D1", 3 if locks >= 3 else locks, "prior PIN locks in 90 days", removed)
    days = age_days(now, card.get("active_since"))
    if days is None: missing.append("card active date for D2")
    else: add(flags, "D2", 2 if days < 30 else 1 if days < 90 else 0, "card active age", removed)
    issue = card.get("other_card_issue")
    if issue not in ("none", "velocity_block", "fraud_alert"): missing.append("other-card security issue for D3")
    else: add(flags, "D3", {"none":0,"velocity_block":1,"fraud_alert":2}[issue], "other debit-card issue", removed)
    days = age_days(now, account.get("opened_at"))
    if days is None: missing.append("account opening date for E1")
    else: add(flags, "E1", 2 if days < 90 else 1 if days < 180 else 0, "account age", removed)
    od = data.get("overdraft_fee_count")
    if not isinstance(od, int) or od < 0: missing.append("overdraft-fee count for E2")
    else: add(flags, "E2", 2 if od >= 2 else 1 if od == 1 else 0, "recent overdraft fees", removed)
    bal = account.get("current_balance")
    if not isinstance(bal, (int,float)): missing.append("current balance for E3")
    else: add(flags, "E3", 2 if bal < 50 else 1 if bal < 100 else 0, "current balance", removed)

    total = sum(x["points"] for x in flags.values())
    level = "LOW" if total <= 4 else "MEDIUM" if total <= 7 else "HIGH" if total <= 10 else "VERY HIGH" if total <= 14 else "CRITICAL"
    escalation = any(x["points"] == 3 for x in flags.values())
    if missing: disposition = "INCOMPLETE—resolve missing fields before an unlock decision"
    elif escalation: disposition = "SUPERVISOR REVIEW REQUIRED—single 3-point flag"
    elif total <= 4: disposition = "eligible for standard-verification unlock if no automatic trigger"
    elif total <= 7: disposition = "ask failed-attempt ownership question before any unlock"
    elif total <= 10: disposition = "ask location/time questions; unlock only with confirmation and satisfactory explanation"
    elif total <= 14: disposition = "do not unlock; callback or enhanced verification required"
    else: disposition = "do not unlock; inspect for unauthorized successes and recommend closure/replacement"
    return {"flags": flags, "total_score": total, "risk_level": level, "single_flag_escalation": escalation, "unknown_fields": missing, "disposition": disposition}

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
