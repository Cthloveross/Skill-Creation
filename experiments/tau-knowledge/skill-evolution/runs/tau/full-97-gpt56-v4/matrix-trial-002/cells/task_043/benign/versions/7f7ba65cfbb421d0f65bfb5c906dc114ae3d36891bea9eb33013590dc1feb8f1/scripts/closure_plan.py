#!/usr/bin/env python3
"""Evaluate supplied closure facts; this script never performs bank actions.

Input JSON keys:
  account_open_date: MM/DD/YYYY (required)
  current_balance: a number or currency string (required)
  as_of_date: YYYY-MM-DD or MM/DD/YYYY (required)
  has_pending_dispute: true, false, or null (required)
  replacement_order_statuses: array of status strings, or null (required)
  annual_fee_reason: boolean (optional; default false)

Output JSON contains blocking_conditions, eligible_to_close, account_age_days,
and, for annual-fee requests, tenure and a waiver expiration recommendation.
"""
import calendar
import datetime as dt
import json
import re
import sys
from decimal import Decimal, InvalidOperation


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("date must use MM/DD/YYYY or YYYY-MM-DD")


def parse_balance(value):
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        raise ValueError("current_balance must be a number or string")
    cleaned = value.strip().replace("$", "").replace(",", "")
    if not re.fullmatch(r"[-+]?\d+(?:\.\d{1,2})?", cleaned):
        raise ValueError("current_balance must be a valid dollar amount")
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError("current_balance is invalid") from exc


def add_one_calendar_year(day):
    target_year = day.year + 1
    target_day = min(day.day, calendar.monthrange(target_year, day.month)[1])
    return dt.date(target_year, day.month, target_day)


def full_years(start, end):
    return end.year - start.year - ((end.month, end.day) < (start.month, start.day))


def main(payload):
    opened = parse_date(payload["account_open_date"])
    as_of = parse_date(payload["as_of_date"])
    if opened > as_of:
        raise ValueError("account_open_date cannot be after as_of_date")
    balance = parse_balance(payload["current_balance"])
    dispute = payload.get("has_pending_dispute")
    statuses = payload.get("replacement_order_statuses")
    if dispute not in (True, False, None):
        raise ValueError("has_pending_dispute must be true, false, or null")
    if statuses is not None and (not isinstance(statuses, list) or not all(isinstance(x, str) for x in statuses)):
        raise ValueError("replacement_order_statuses must be an array of strings or null")

    blockers = []
    age_days = (as_of - opened).days
    if balance != Decimal("0.00"):
        blockers.append("outstanding_balance_not_zero")
    if dispute is True:
        blockers.append("pending_dispute")
    elif dispute is None:
        blockers.append("pending_dispute_status_unknown")
    if age_days < 60:
        blockers.append("account_younger_than_60_days")
    if statuses is None:
        blockers.append("replacement_order_status_unknown")
    else:
        final = {"delivered", "cancelled"}
        if any(status.strip().lower() not in final for status in statuses):
            blockers.append("pending_replacement_order")

    result = {
        "account_age_days": age_days,
        "blocking_conditions": blockers,
        "eligible_to_close": not blockers,
        "next_step": "continue_eligibility_and_retention_workflow" if not blockers else "resolve_all_blocking_conditions_before_retention_or_closure",
    }
    if payload.get("annual_fee_reason", False):
        years = full_years(opened, as_of)
        result["customer_tenure_full_years"] = years
        if years >= 2:
            result["annual_fee_option"] = "one_year_waiver_if_customer_accepts"
            result["waiver_expiration_date"] = add_one_calendar_year(as_of).strftime("%m/%d/%Y")
        else:
            result["annual_fee_option"] = "offer_same_category_no_annual_fee_downgrade_if_customer_accepts"
    return result


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), sort_keys=True))
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
