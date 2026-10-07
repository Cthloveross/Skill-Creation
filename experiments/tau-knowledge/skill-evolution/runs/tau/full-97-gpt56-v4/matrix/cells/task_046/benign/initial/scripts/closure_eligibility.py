#!/usr/bin/env python3
"""Deterministically evaluate credit-card closure prerequisites.

Reads one JSON object from stdin and writes one JSON object to stdout. This is
advisory only: it does not call banking tools or establish customer identity.
"""
import json
import re
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("date must use MM/DD/YYYY or YYYY-MM-DD")


def parse_current_date(value):
    if not isinstance(value, str):
        raise ValueError("current_time must be a string")
    value = value.strip()
    # Banking time values may include a timezone abbreviation; only calendar date
    # is needed for the stated age requirement.
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", value)
    if match:
        return parse_date(match.group(1))
    return parse_date(value)


def cents(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("current_balance is required")
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("current_balance is not a monetary amount") from exc
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("account"), dict):
        raise ValueError("account object is required")
    account = payload["account"]
    opened = parse_date(account.get("date_of_account_open"))
    today = parse_current_date(payload.get("current_time"))
    if opened > today:
        raise ValueError("date_of_account_open cannot be in the future")
    balance = cents(account.get("current_balance"))
    age_days = (today - opened).days
    disputes = payload.get("pending_disputes")
    replacements = payload.get("pending_replacement_cards")
    reasons = []
    if balance != 0:
        reasons.append("outstanding_balance")
    if disputes is not False:
        reasons.append("pending_disputes" if disputes is True else "pending_disputes_unknown")
    if replacements is not False:
        reasons.append("pending_replacement_card" if replacements is True else "pending_replacement_card_unknown")
    if age_days < 60:
        reasons.append("account_under_60_days")
    return {
        "eligible": not reasons,
        "account_age_days": age_days,
        "balance_cents": balance,
        "pending_disputes": disputes,
        "pending_replacement_cards": replacements,
        "blocking_reasons": reasons,
    }


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        print(json.dumps(main(request), separators=(",", ":"), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"eligible": False, "error": str(exc), "blocking_reasons": ["invalid_input"]}, separators=(",", ":")))
        sys.exit(2)
