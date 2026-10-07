#!/usr/bin/env python3
"""Conservative deterministic evaluator for normalized card-closure checks.

Reads one JSON object from stdin and writes one JSON result to stdout. This helper
never calls banking tools and does not replace review of account/dispute ownership.
"""
import json
import re
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled", "canceled"}
DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y")


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("date is missing")
    text = value.strip()
    # ISO timestamps may include a timezone; only the calendar-date component is needed.
    if len(text) >= 10 and re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError("unsupported date format")


def parse_money(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("balance is missing")
    text = str(value).strip().replace(",", "")
    text = re.sub(r"^[^0-9+\-.]+", "", text)
    if not text:
        raise ValueError("balance is missing")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("invalid balance") from exc


def main(payload):
    blockers = []
    age_days = None

    try:
        today = parse_date(payload.get("as_of"))
        opened = parse_date(payload.get("account_open_date"))
        age_days = (today - opened).days
        if age_days < 0:
            blockers.append({"code": "invalid_account_open_date", "message": "Account opening date is in the future."})
        elif age_days < 60:
            blockers.append({"code": "account_too_new", "message": "Account must be open at least 60 days.", "age_days": age_days})
    except ValueError as exc:
        blockers.append({"code": "account_age_unknown", "message": str(exc)})

    try:
        balance = parse_money(payload.get("current_balance"))
        if balance != Decimal("0"):
            blockers.append({"code": "nonzero_balance", "message": "Outstanding balance must be exactly zero.", "balance": str(balance)})
    except ValueError as exc:
        blockers.append({"code": "balance_unknown", "message": str(exc)})

    pending = payload.get("pending_disputes")
    if pending is not True and pending is not False:
        blockers.append({"code": "dispute_status_unknown", "message": "Pending-dispute result must be a boolean."})
    elif pending:
        blockers.append({"code": "pending_dispute", "message": "Active or pending disputes block closure."})

    statuses = payload.get("replacement_statuses")
    if not isinstance(statuses, list) or any(not isinstance(s, str) or not s.strip() for s in statuses):
        blockers.append({"code": "replacement_status_unknown", "message": "Replacement statuses must be an array of nonempty strings."})
    else:
        nonfinal = [s for s in statuses if s.strip().lower() not in FINAL_REPLACEMENT_STATUSES]
        if nonfinal:
            blockers.append({"code": "pending_replacement", "message": "A non-final replacement order blocks closure.", "statuses": nonfinal})

    return {"eligible": not blockers, "age_days": age_days, "blockers": blockers}


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        result = main(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        result = {"eligible": False, "age_days": None, "blockers": [{"code": "invalid_input", "message": str(exc)}]}
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
