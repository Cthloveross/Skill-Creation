#!/usr/bin/env python3
"""Read-only debit-card closure and replacement eligibility assessment.

Reads one JSON object from stdin and writes one JSON object to stdout.  It makes no
banking calls and is intentionally conservative: absent data is reported as UNKNOWN.
"""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

REPLACEMENT_REASONS = {"lost", "stolen", "fraud", "damaged"}
TIERS = {
    "ENTRY": {"limit": 2, "wait_hours": 48,
              "shipping": {"STANDARD": "0.00"},
              "design": {"CLASSIC": "0.00", "PREMIUM": "10.00", "CUSTOM": "25.00"},
              "excess_fee": "25.00"},
    "MID": {"limit": 3, "wait_hours": 0,
            "shipping": {"STANDARD": "0.00", "EXPEDITED": "15.00"},
            "design": {"CLASSIC": "0.00", "PREMIUM": "10.00", "CUSTOM": "25.00"},
            "excess_fee": "15.00"},
    "PREMIUM": {"limit": 5, "wait_hours": 0,
                "shipping": {"STANDARD": "0.00", "EXPEDITED": "0.00", "RUSH": "35.00"},
                "design": {"CLASSIC": "0.00", "PREMIUM": "0.00", "CUSTOM": "15.00"},
                "excess_fee": None},
    "ELITE": {"limit": None, "wait_hours": 0,
              "shipping": {"STANDARD": "0.00", "EXPEDITED": "0.00", "RUSH": "0.00"},
              "design": {"CLASSIC": "0.00", "PREMIUM": "0.00", "CUSTOM": "0.00"},
              "excess_fee": None},
}

def parse_date(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None

def decimal_value(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None

def business_days_between(start, end):
    """Count weekdays after start through end, suitable for an account opening age."""
    if not start or not end or end < start:
        return None
    days = 0
    cursor = start
    while cursor < end:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            days += 1
    return days

def main(data):
    today = parse_date(data.get("current_date"))
    accounts = data.get("accounts") if isinstance(data.get("accounts"), list) else []
    cards = data.get("cards") if isinstance(data.get("cards"), list) else []
    lost_ids = data.get("lost_card_ids") if isinstance(data.get("lost_card_ids"), list) else []
    by_account = {str(a.get("account_id")): a for a in accounts if a.get("account_id") is not None}
    by_id = {str(c.get("card_id")): c for c in cards if c.get("card_id") is not None}
    pending_map = data.get("pending_transactions_by_account") or {}
    for tx in data.get("transactions") or []:
        if str(tx.get("status", "")).lower() in {"pending", "processing"} and tx.get("account_id") is not None:
            pending_map[str(tx["account_id"])] = True
    refunds = data.get("pending_refunds_by_card") or {}
    closure_times = data.get("closure_times") or {}
    result = {"cards": [], "accounts": [], "unknown_lost_card_ids": [], "input_warnings": []}
    if not today:
        result["input_warnings"].append("current_date is missing or unparseable")

    selected_accounts = set()
    for card_id in lost_ids:
        card = by_id.get(str(card_id))
        if not card:
            result["unknown_lost_card_ids"].append(card_id)
            continue
        account_id = str(card.get("account_id"))
        selected_accounts.add(account_id)
        status = str(card.get("status", "")).upper()
        freeze = []
        if status != "ACTIVE":
            freeze.append("card status must be ACTIVE to freeze")
        close = []
        if status not in {"ACTIVE", "PENDING"}:
            close.append("card status must be ACTIVE or PENDING under documented closure rule")
        pending = pending_map.get(account_id)
        if pending is True:
            close.append("pending or processing account transaction")
        elif pending is None:
            close.append("UNKNOWN pending transaction status")
        refund = refunds.get(str(card_id))
        if refund is True:
            close.append("pending refund")
        elif refund is None:
            close.append("UNKNOWN pending refund status")
        # Lost/stolen closure bypasses card-age rule, so no age blocker is added here.
        result["cards"].append({
            "card_id": card_id, "account_id": card.get("account_id"), "status": status or "UNKNOWN",
            "freeze_eligible": not freeze, "freeze_blockers": freeze,
            "closure_eligible_under_documented_rule": not close, "closure_blockers": close,
            "closure_reason": "lost"
        })

    for account_id in sorted(selected_accounts):
        account = by_account.get(account_id)
        blockers = []
        if not account:
            result["accounts"].append({"account_id": account_id, "replacement_blockers": ["UNKNOWN linked account"]})
            continue
        tier = str(account.get("account_class", "")).upper()
        rules = TIERS.get(tier)
        if str(account.get("account_type", "")).lower() != "checking":
            blockers.append("account is not a checking account")
        if str(account.get("status", "")).upper() != "OPEN":
            blockers.append("account is not OPEN")
        opened = parse_date(account.get("date_opened"))
        age = business_days_between(opened, today) if today else None
        if age is None:
            blockers.append("UNKNOWN account opening age")
        elif age < 3:
            blockers.append("account has been open fewer than 3 business days")
        balance = decimal_value(account.get("balance"))
        if balance is None:
            blockers.append("UNKNOWN account balance")
        elif balance < Decimal("25"):
            blockers.append("balance is below $25 minimum")
        address_ok = account.get("valid_us_address", data.get("valid_us_address"))
        if address_ok is not True:
            blockers.append("UNKNOWN or invalid US domestic mailing address")
        age_years = data.get("customer_age")
        if age_years is None:
            blockers.append("UNKNOWN customer age")
        else:
            try:
                if int(age_years) < 18:
                    blockers.append("customer is under 18")
            except (ValueError, TypeError):
                blockers.append("UNKNOWN customer age")
        current_cards = [c for c in cards if str(c.get("account_id")) == account_id]
        if any(str(c.get("status", "")).upper() == "ACTIVE" for c in current_cards):
            blockers.append("an ACTIVE debit card remains on account")
        if any(str(c.get("status", "")).upper() == "PENDING" for c in current_cards):
            blockers.append("a PENDING debit-card order remains on account")
        if not rules:
            blockers.append("UNKNOWN account tier")
            schedule = None
            replacement_count = None
        else:
            cutoff = today - timedelta(days=365) if today else None
            dated = [parse_date(c.get("date_issued")) for c in current_cards
                     if str(c.get("issue_reason", "")).lower() in REPLACEMENT_REASONS]
            if cutoff is None or any(d is None for d in dated):
                replacement_count = None
                blockers.append("UNKNOWN replacement-history date")
            else:
                replacement_count = sum(d >= cutoff for d in dated)
                if rules["limit"] is not None and replacement_count >= rules["limit"]:
                    if rules["excess_fee"] is None:
                        blockers.append("replacement limit reached; must wait for oldest qualifying replacement to age out")
                    else:
                        blockers.append("replacement limit reached; wait or obtain explicit excess-fee election")
            schedule = {"tier": tier, "shipping_fees": rules["shipping"], "design_fees": rules["design"],
                        "excess_replacement_fee": rules["excess_fee"]}
            if rules["wait_hours"]:
                selected = [str(c.get("card_id")) for c in current_cards if str(c.get("card_id")) in map(str, lost_ids)]
                if any(cid not in closure_times for cid in selected):
                    blockers.append("closure time required for 48-hour ENTRY replacement wait")
        result["accounts"].append({"account_id": account_id, "tier": tier or "UNKNOWN",
                                   "account_business_days_open": age,
                                   "qualifying_replacements_last_12_months": replacement_count,
                                   "fee_schedule": schedule, "replacement_blockers": blockers})
    return result

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
