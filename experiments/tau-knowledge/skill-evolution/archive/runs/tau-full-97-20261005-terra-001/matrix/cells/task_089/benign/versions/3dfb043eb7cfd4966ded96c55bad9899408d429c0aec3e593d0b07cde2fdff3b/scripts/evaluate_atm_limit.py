#!/usr/bin/env python3
"""Assess documented eligibility and capacity for one temporary ATM-limit request.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
performs no network access and no banking action.
"""

import json
import re
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


MONEY = Decimal("0.01")


def money(value):
    """Return a non-negative Decimal or raise ValueError."""
    if isinstance(value, bool) or value is None:
        raise ValueError("must be a numeric amount")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("must be a numeric amount")
    if not result.is_finite() or result < 0:
        raise ValueError("must be a non-negative finite amount")
    return result


def fmt(value):
    return format(value.quantize(MONEY, rounding=ROUND_HALF_UP), ".2f")


def parse_date(value):
    """Parse the date portion of common tool timestamps without timezone guessing."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing or invalid date")
    text = value.strip()
    # Tool timestamps can end in a timezone abbreviation unsupported by fromisoformat.
    text = re.sub(r"\s+[A-Za-z]{2,5}$", "", text)
    candidates = ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S")
    for pattern in candidates:
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError("unsupported date format") from exc


def check(label, state, detail):
    return {"check": label, "state": state, "detail": detail}


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")

    missing = []
    checks = []
    diagnosis = []
    account = payload.get("account")
    card = payload.get("card")
    transactions = payload.get("transactions")

    try:
        today = parse_date(payload.get("as_of"))
    except ValueError:
        today = None
        missing.append("as_of: supply the current runtime date or timestamp")

    if not isinstance(account, dict):
        account = {}
        missing.append("account")
    if not isinstance(card, dict):
        card = {}
        missing.append("card")

    account_status = account.get("status")
    if account_status is None:
        checks.append(check("account_open", "unknown", "Account status was not supplied."))
        missing.append("account.status")
    elif str(account_status).upper() == "OPEN":
        checks.append(check("account_open", "pass", "Linked account status is OPEN."))
    else:
        checks.append(check("account_open", "fail", "Linked account status is not OPEN."))

    account_type = account.get("account_type")
    if account_type is None:
        checks.append(check("checking_account", "unknown", "Account type was not supplied."))
        missing.append("account.account_type")
    elif str(account_type).lower() == "checking":
        checks.append(check("checking_account", "pass", "Linked account is a checking account."))
    else:
        checks.append(check("checking_account", "fail", "Linked account is not a checking account."))

    card_status = card.get("status")
    if card_status is None:
        checks.append(check("card_active", "unknown", "Card status was not supplied."))
        missing.append("card.status")
    elif str(card_status).upper() == "ACTIVE":
        checks.append(check("card_active", "pass", "Card status is ACTIVE."))
    else:
        checks.append(check("card_active", "fail", "Card status is not ACTIVE."))

    opened = None
    try:
        opened = parse_date(account.get("date_opened"))
    except ValueError:
        checks.append(check("account_age_60_days", "unknown", "Account opening date was not supplied or is invalid."))
        missing.append("account.date_opened")
    if opened is not None and today is None:
        checks.append(check("account_age_60_days", "unknown", "Current runtime date is required."))
    elif opened is not None:
        if opened > today:
            checks.append(check("account_age_60_days", "fail", "Account opening date is in the future."))
        elif opened <= today - timedelta(days=60):
            checks.append(check("account_age_60_days", "pass", "Account is at least 60 days old."))
        else:
            checks.append(check("account_age_60_days", "fail", "Account is younger than 60 days."))

    overdrafts = []
    if not isinstance(transactions, list):
        checks.append(check("no_overdraft_fee_last_30_days", "unknown", "Transaction history was not supplied."))
        missing.append("transactions")
    elif today is None:
        checks.append(check("no_overdraft_fee_last_30_days", "unknown", "Current runtime date is required."))
    else:
        window_start = today - timedelta(days=30)
        unparseable = False
        for transaction in transactions:
            if not isinstance(transaction, dict):
                unparseable = True
                continue
            if str(transaction.get("type", "")).lower() != "overdraft_fee":
                continue
            try:
                txn_date = parse_date(transaction.get("date"))
            except ValueError:
                unparseable = True
                continue
            if window_start <= txn_date <= today:
                overdrafts.append(txn_date.isoformat())
        if unparseable:
            checks.append(check("no_overdraft_fee_last_30_days", "unknown", "One or more transaction dates cannot be evaluated."))
            missing.append("valid transaction dates")
        elif overdrafts:
            checks.append(check("no_overdraft_fee_last_30_days", "fail", "Overdraft fee activity exists within the 30-day window."))
        else:
            checks.append(check("no_overdraft_fee_last_30_days", "pass", "No overdraft fee activity was found in the 30-day window."))

    current_limit = None
    used = None
    try:
        current_limit = money(card.get("daily_atm_limit"))
    except ValueError:
        missing.append("card.daily_atm_limit")
        diagnosis.append("Current ATM limit is unavailable.")
    try:
        if "daily_atm_used" in card and card.get("daily_atm_used") is not None:
            used = money(card.get("daily_atm_used"))
        else:
            missing.append("card.daily_atm_used")
            diagnosis.append("Daily ATM usage is unavailable, so remaining ATM capacity cannot be calculated.")
    except ValueError:
        missing.append("card.daily_atm_used")
        diagnosis.append("Daily ATM usage is invalid, so remaining ATM capacity cannot be calculated.")

    remaining = None
    if current_limit is not None and used is not None:
        remaining = max(current_limit - used, Decimal("0"))
        diagnosis.append("Remaining ATM capacity was calculated from the card's current limit and usage.")

    attempt = None
    if payload.get("attempt_amount") is not None:
        try:
            attempt = money(payload.get("attempt_amount"))
            if remaining is not None:
                if attempt > remaining:
                    diagnosis.append("The attempted withdrawal exceeds the calculated remaining ATM capacity.")
                else:
                    diagnosis.append("The attempted withdrawal does not exceed calculated remaining ATM capacity; check other decline causes.")
        except ValueError:
            missing.append("attempt_amount: must be a non-negative numeric amount")

    requested = None
    if payload.get("requested_new_limit") is not None:
        try:
            requested = money(payload.get("requested_new_limit"))
            if requested <= 0:
                checks.append(check("requested_limit_within_150_percent", "fail", "Requested new limit must be positive."))
            elif current_limit is None:
                checks.append(check("requested_limit_within_150_percent", "unknown", "Current ATM limit is required."))
            elif requested <= current_limit * Decimal("1.5"):
                checks.append(check("requested_limit_within_150_percent", "pass", "Requested new limit is no more than 150% of current limit."))
            else:
                checks.append(check("requested_limit_within_150_percent", "fail", "Requested new limit exceeds 150% of current limit."))
        except ValueError:
            missing.append("requested_new_limit: must be a non-negative numeric amount")
    else:
        checks.append(check("requested_limit_within_150_percent", "unknown", "No customer-authorized new daily limit was supplied."))

    frequency = payload.get("temporary_increase_in_last_24h")
    if frequency is True:
        checks.append(check("no_temporary_increase_last_24_hours", "fail", "A temporary increase was already made for this card in the prior 24 hours."))
    elif frequency is False:
        checks.append(check("no_temporary_increase_last_24_hours", "pass", "No temporary increase was recorded for this card in the prior 24 hours."))
    else:
        checks.append(check("no_temporary_increase_last_24_hours", "unknown", "Prior-24-hour temporary-increase history was not established."))
        missing.append("temporary_increase_in_last_24h")

    states = [item["state"] for item in checks]
    required_names = {
        "account_open",
        "checking_account",
        "card_active",
        "account_age_60_days",
        "no_overdraft_fee_last_30_days",
        "requested_limit_within_150_percent",
        "no_temporary_increase_last_24_hours",
    }
    required = [item for item in checks if item["check"] in required_names]
    if any(item["state"] == "fail" for item in required):
        approval_status = "ineligible"
    elif any(item["state"] == "unknown" for item in required):
        approval_status = "insufficient_data"
    else:
        approval_status = "eligible"

    output = {
        "approval_status": approval_status,
        "checks": checks,
        "diagnosis": diagnosis,
        "missing_data": sorted(set(missing)),
        "current_atm_limit": fmt(current_limit) if current_limit is not None else None,
        "daily_atm_used": fmt(used) if used is not None else None,
        "remaining_atm_capacity": fmt(remaining) if remaining is not None else None,
        "maximum_permitted_new_limit": fmt(current_limit * Decimal("1.5")) if current_limit is not None else None,
        "minimum_limit_to_cover_attempt_if_usage_is_correct": fmt(used + attempt) if used is not None and attempt is not None else None,
        "overdraft_fee_dates_in_window": overdrafts,
    }
    return output


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        result = main(raw)
        print(json.dumps(result, sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
