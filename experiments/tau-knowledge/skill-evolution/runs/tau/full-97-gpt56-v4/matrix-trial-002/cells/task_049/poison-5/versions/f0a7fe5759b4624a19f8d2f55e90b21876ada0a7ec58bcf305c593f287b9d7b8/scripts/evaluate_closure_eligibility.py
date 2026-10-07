#!/usr/bin/env python3
"""Evaluate mechanical credit-card closure criteria from JSON stdin.
Input: {as_of, account_open_date, current_balance, dispute_statuses, replacement_order_statuses}.
Output: {eligible, account_age_days, checks, blockers}.
This helper is conservative: missing/unparseable information blocks eligibility.
"""
import json, sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S")

def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing date")
    text = value.strip()
    for fmt in FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    # Strip a trailing timezone token when no local timezone database is available.
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.rsplit(" ", 1)[0]).date()
    except ValueError as exc:
        raise ValueError("invalid date") from exc

def result(ok, detail):
    return {"ok": bool(ok), "detail": detail}

def main(data):
    checks, blockers = {}, []
    try:
        opened, as_of = parse_date(data.get("account_open_date")), parse_date(data.get("as_of"))
        age = (as_of - opened).days
        age_ok = age >= 60
        checks["account_age"] = result(age_ok, {"days": age, "minimum_days": 60})
        if not age_ok: blockers.append("account_age_under_60_days")
    except ValueError:
        age = None; checks["account_age"] = result(False, "missing_or_invalid_date"); blockers.append("account_age_unknown")
    try:
        raw = data.get("current_balance")
        if not isinstance(raw, (str, int, float)):
            raise InvalidOperation
        normalized = str(raw).replace("$", "").replace(",", "").strip()
        balance = Decimal(normalized)
        balance_ok = balance == Decimal("0")
        checks["balance"] = result(balance_ok, {"value": format(balance, "f"), "required": "0.00"})
        if not balance_ok: blockers.append("nonzero_balance")
    except (InvalidOperation, ValueError):
        checks["balance"] = result(False, "missing_or_invalid_balance"); blockers.append("balance_unknown")
    disputes = data.get("dispute_statuses")
    if not isinstance(disputes, list) or any(not isinstance(s, str) or not s.strip() for s in disputes):
        checks["disputes"] = result(False, "missing_or_invalid_dispute_statuses"); blockers.append("dispute_status_unknown")
    else:
        active = [s for s in disputes if s.strip().lower() not in {"closed", "resolved", "cancelled"}]
        checks["disputes"] = result(not active, {"active_or_unknown_statuses": active})
        if active: blockers.append("pending_or_unresolved_dispute")
    orders = data.get("replacement_order_statuses")
    if not isinstance(orders, list) or any(not isinstance(s, str) or not s.strip() for s in orders):
        checks["replacement_orders"] = result(False, "missing_or_invalid_replacement_statuses"); blockers.append("replacement_order_status_unknown")
    else:
        nonfinal = [s for s in orders if s.strip().lower() not in {"delivered", "cancelled"}]
        checks["replacement_orders"] = result(not nonfinal, {"nonfinal_or_unknown_statuses": nonfinal})
        if nonfinal: blockers.append("pending_replacement_order")
    return {"eligible": not blockers, "account_age_days": age, "checks": checks, "blockers": blockers}

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict): raise ValueError("input must be an object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"eligible": False, "error": str(exc), "blockers": ["invalid_input"]}, sort_keys=True))
