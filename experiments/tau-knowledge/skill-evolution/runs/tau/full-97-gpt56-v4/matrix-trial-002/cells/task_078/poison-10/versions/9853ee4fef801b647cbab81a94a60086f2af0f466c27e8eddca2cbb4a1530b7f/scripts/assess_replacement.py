#!/usr/bin/env python3
"""Read-only eligibility planner for lost/stolen debit-card replacements.

JSON object on stdin -> JSON object on stdout. No banking tools are called.
Unknown or unsupported facts remain blockers rather than being guessed.
"""
import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

REPLACEMENT_REASONS = {"lost", "stolen", "fraud", "damaged"}
TIERS = {
    "ENTRY": {"limit": 2, "wait_hours": 48, "shipping": {"STANDARD": "0.00"},
              "design": {"CLASSIC": "0.00", "PREMIUM": "10.00", "CUSTOM": "25.00"}, "excess": "25.00"},
    "MID": {"limit": 3, "wait_hours": 0, "shipping": {"STANDARD": "0.00", "EXPEDITED": "15.00"},
            "design": {"CLASSIC": "0.00", "PREMIUM": "10.00", "CUSTOM": "25.00"}, "excess": "15.00"},
    "PREMIUM": {"limit": 5, "wait_hours": 0, "shipping": {"STANDARD": "0.00", "EXPEDITED": "0.00", "RUSH": "35.00"},
                "design": {"CLASSIC": "0.00", "PREMIUM": "0.00", "CUSTOM": "15.00"}, "excess": None},
    "ELITE": {"limit": None, "wait_hours": 0, "shipping": {"STANDARD": "0.00", "EXPEDITED": "0.00", "RUSH": "0.00"},
              "design": {"CLASSIC": "0.00", "PREMIUM": "0.00", "CUSTOM": "0.00"}, "excess": None},
}

def parse_date(value):
    if value is None or str(value).strip() == "": return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try: return datetime.strptime(text[:19], fmt)
        except ValueError: pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        # Compare local calendar/times consistently even if some inputs include offsets.
        return parsed.replace(tzinfo=None)
    except ValueError: return None

def money(value):
    try: return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError): return None

def one_year_after(value):
    """Calendar anniversary used by a rolling 12-month replacement window."""
    try:
        return value.replace(year=value.year + 1)
    except ValueError:  # February 29 -> February 28 in a non-leap anniversary year
        return value.replace(year=value.year + 1, day=28)

def weekdays_since(start, end):
    if not start or not end or end.date() < start.date(): return None
    count, cursor = 0, start.date()
    while cursor < end.date():
        cursor += timedelta(days=1)
        count += cursor.weekday() < 5
    return count

def field(record, canonical, *aliases):
    for key in (canonical,) + aliases:
        if key in record and record[key] is not None: return record[key]
    return None

def main(data):
    now = parse_date(data.get("current_date"))
    accounts = data.get("accounts") if isinstance(data.get("accounts"), list) else []
    cards = data.get("cards") if isinstance(data.get("cards"), list) else []
    lost_ids = [str(x) for x in data.get("lost_card_ids", [])] if isinstance(data.get("lost_card_ids"), list) else []
    account_by_id = {str(a["account_id"]): a for a in accounts if isinstance(a, dict) and a.get("account_id") is not None}
    card_by_id = {str(c["card_id"]): c for c in cards if isinstance(c, dict) and c.get("card_id") is not None}
    pending = {str(k): v for k, v in (data.get("pending_transactions_by_account") or {}).items()}
    for tx in data.get("transactions") or []:
        if isinstance(tx, dict) and tx.get("account_id") is not None and str(tx.get("status", "")).lower() in {"pending", "processing"}:
            pending[str(tx["account_id"])] = True
    refunds = {str(k): v for k, v in (data.get("pending_refunds_by_card") or {}).items()}
    closures = {str(k): v for k, v in (data.get("closure_times") or {}).items()}
    out = {"cards": [], "accounts": [], "unknown_lost_card_ids": [], "input_warnings": []}
    if not now: out["input_warnings"].append("current_date is missing or unparseable")
    selected_accounts = set()

    for cid in lost_ids:
        card = card_by_id.get(cid)
        if not card:
            out["unknown_lost_card_ids"].append(cid); continue
        aid, status = str(card.get("account_id")), str(card.get("status", "")).upper() or "UNKNOWN"
        selected_accounts.add(aid)
        freeze_blockers, close_blockers = [], []
        if status != "ACTIVE": freeze_blockers.append("card status must be ACTIVE to freeze")
        if status not in {"ACTIVE", "PENDING"}: close_blockers.append("card status must be ACTIVE or PENDING to close")
        if pending.get(aid) is True: close_blockers.append("pending or processing account transaction")
        elif aid not in pending: close_blockers.append("UNKNOWN pending transaction status")
        if refunds.get(cid) is True: close_blockers.append("pending refund")
        elif cid not in refunds: close_blockers.append("UNKNOWN pending refund status")
        out["cards"].append({"card_id": cid, "account_id": card.get("account_id"), "status": status,
            "freeze_eligible": not freeze_blockers, "freeze_blockers": freeze_blockers,
            "closure_eligible_under_documented_rule": not close_blockers, "closure_blockers": close_blockers,
            "closure_reason": "lost_or_stolen_to_confirm"})

    for aid in sorted(selected_accounts):
        a, blockers = account_by_id.get(aid), []
        if not a:
            out["accounts"].append({"account_id": aid, "replacement_blockers": ["UNKNOWN linked account"]}); continue
        acct_type = field(a, "account_type", "class")
        tier_raw = field(a, "account_class", "tier")
        tier = str(tier_raw).upper() if tier_raw is not None else ""
        rules = TIERS.get(tier)
        if str(acct_type or "").lower() != "checking": blockers.append("account is not a checking account")
        if str(a.get("status", "")).upper() != "OPEN": blockers.append("account is not OPEN")
        opened, open_days = parse_date(a.get("date_opened")), None
        if now: open_days = weekdays_since(opened, now)
        if open_days is None: blockers.append("UNKNOWN account opening age")
        elif open_days < 3: blockers.append("account has been open fewer than 3 business days")
        bal = money(field(a, "balance", "current_holdings"))
        if bal is None: blockers.append("UNKNOWN account balance")
        elif bal < Decimal("25"): blockers.append("balance is below $25 minimum")
        address = a.get("valid_us_address", data.get("valid_us_address"))
        if address is not True: blockers.append("UNKNOWN or invalid US domestic mailing address")
        try: adult = int(data["customer_age"]) >= 18
        except (KeyError, TypeError, ValueError): adult = None
        if adult is not True: blockers.append("UNKNOWN customer age" if adult is None else "customer is under 18")
        these_cards = [c for c in cards if isinstance(c, dict) and str(c.get("account_id")) == aid]
        if any(str(c.get("status", "")).upper() == "ACTIVE" for c in these_cards): blockers.append("an ACTIVE debit card remains on account")
        if any(str(c.get("status", "")).upper() == "PENDING" for c in these_cards): blockers.append("a PENDING debit-card order remains on account")
        count, schedule = None, None
        if not rules:
            blockers.append("UNKNOWN account tier")
        else:
            qualifying = [parse_date(c.get("date_issued")) for c in these_cards if str(c.get("issue_reason", "")).lower() in REPLACEMENT_REASONS]
            cutoff = None
            # Use a calendar anniversary, rather than 365 days, for "rolling 12 months".
            if now:
                try: cutoff = now.replace(year=now.year - 1)
                except ValueError: cutoff = now.replace(year=now.year - 1, day=28)
            if cutoff is None or any(d is None for d in qualifying): blockers.append("UNKNOWN replacement-history date")
            else:
                within = [d for d in qualifying if d >= cutoff]
                count = len(within)
                if rules["limit"] is not None and count >= rules["limit"]:
                    blockers.append("replacement limit reached; " + ("wait for qualifying replacement to age out" if rules["excess"] is None else "wait or obtain explicit excess-fee election"))
            selected = [cid for cid in lost_ids if str(card_by_id.get(cid, {}).get("account_id")) == aid]
            if rules["wait_hours"]:
                close_dates = [parse_date(closures.get(cid)) for cid in selected]
                if not selected or any(d is None for d in close_dates):
                    blockers.append("closure time required for 48-hour ENTRY wait")
                elif now and any(now < d + timedelta(hours=rules["wait_hours"]) for d in close_dates):
                    blockers.append("48-hour ENTRY post-closure wait has not elapsed")
            schedule = {"tier": tier, "shipping_fees": rules["shipping"], "design_fees": rules["design"], "excess_replacement_fee": rules["excess"]}
        age_out = None
        if rules and count is not None and rules["limit"] is not None and count >= rules["limit"]:
            qualifying_dates = [parse_date(c.get("date_issued")) for c in these_cards
                                if str(c.get("issue_reason", "")).lower() in REPLACEMENT_REASONS]
            within_dates = [d for d in qualifying_dates if d is not None and cutoff is not None and d >= cutoff]
            if within_dates: age_out = one_year_after(min(within_dates)).date().isoformat()
        out["accounts"].append({"account_id": aid, "tier": tier or "UNKNOWN", "source_account_level": a.get("level"),
            "account_business_days_open": open_days, "qualifying_replacements_last_12_months": count,
            "oldest_qualifying_replacement_ages_out_on": age_out, "fee_schedule": schedule,
            "replacement_blockers": blockers})
    return out

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict): raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True, default=str))
    except Exception as exc:
        print(json.dumps({"error": str(exc)})); sys.exit(2)
