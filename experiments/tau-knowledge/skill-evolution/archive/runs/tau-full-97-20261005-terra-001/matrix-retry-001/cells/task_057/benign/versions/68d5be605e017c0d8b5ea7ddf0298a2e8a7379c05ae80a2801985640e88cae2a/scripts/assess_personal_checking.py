#!/usr/bin/env python3
"""Assess documented personal-checking opening prerequisites.

Reads one JSON object from stdin and emits one JSON object to stdout. This
program is deliberately side-effect free: it does not call banking tools.
"""

import calendar
import json
import re
import sys
from datetime import date, datetime


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    # The supported current-time output may include a trailing timezone label
    # such as " EST", which is not needed for date-only policy comparison.
    text = re.sub(r"\s+[A-Za-z]{2,5}$", "", text)
    candidates = [text]
    if "T" in text:
        candidates.append(text.split("T", 1)[0])
    if " " in text:
        candidates.append(text.split(" ", 1)[0])
    for candidate in candidates:
        candidate = candidate.rstrip("Z")
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass
        for fmt in ("%m/%d/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    return None


def subtract_calendar_months(day, months):
    month_index = day.year * 12 + (day.month - 1) - months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def is_for_cause(record):
    value = record.get("closed_for_cause")
    if value is True:
        return True
    if value is False:
        return False
    value = record.get("closure_reason")
    if isinstance(value, str):
        return value.strip().lower().replace("-", " ").replace("_", " ") in {
            "for cause", "cause"
        }
    return None


def is_closed(record):
    status = record.get("status")
    return isinstance(status, str) and status.strip().upper() == "CLOSED"


def main(payload):
    if not isinstance(payload, dict):
        return {
            "decision": "incomplete",
            "failures": [],
            "unknowns": ["Input must be a JSON object."],
        }

    failures = []
    unknowns = []
    identity_verified = payload.get("identity_verified")
    if identity_verified is not True:
        if identity_verified is False:
            failures.append("Customer identity has not been verified.")
        else:
            unknowns.append(
                "identity_verified must be explicitly true after logged two-field verification."
            )

    as_of = parse_date(payload.get("as_of"))
    if as_of is None:
        unknowns.append(
            "A parseable current as_of date is required for the six-month closure review."
        )
        lookback = None
    else:
        lookback = subtract_calendar_months(as_of, 6)

    accounts = payload.get("accounts")
    personal = []
    if not isinstance(accounts, list):
        unknowns.append("accounts must be a normalized array from account lookup.")
        accounts = []
    else:
        for index, record in enumerate(accounts):
            if not isinstance(record, dict):
                unknowns.append("Account record %d is not an object." % index)
                continue
            if record.get("is_personal_checking") is True:
                personal.append((index, record))
            elif record.get("is_personal_checking") is None:
                account_type = str(record.get("account_type", "")).strip().lower()
                if "checking" in account_type:
                    unknowns.append(
                        "Checking record %d has no resolved is_personal_checking classification."
                        % index
                    )

    count = len(personal)
    # This applies the stated current-portfolio condition exactly: no more
    # than four personal checking accounts.
    if count > 4:
        failures.append(
            "Customer has %d personal checking accounts, exceeding the maximum of 4."
            % count
        )

    for index, record in personal:
        if not is_closed(record):
            continue
        cause = is_for_cause(record)
        if cause is True:
            closed_on = parse_date(record.get("closed_date") or record.get("date_closed"))
            if closed_on is None:
                unknowns.append(
                    "Closed personal checking record %d is for cause but has no usable closure date."
                    % index
                )
            elif lookback is not None and closed_on >= lookback:
                failures.append(
                    "Personal checking record %d was closed for cause on %s, within the six-month lookback."
                    % (index, closed_on.isoformat())
                )
        elif cause is None:
            unknowns.append(
                "Closed personal checking record %d lacks closure-cause information." % index
            )

    selection = payload.get("desired_account_class")
    selection_ok = isinstance(selection, str) and bool(selection.strip())
    if not selection_ok:
        unknowns.append("An exact desired_account_class is required.")
    elif payload.get("account_class_confirmed_exact") is not True:
        unknowns.append(
            "The desired account class has not been confirmed as an exact official class."
        )

    official = payload.get("official_account_classes")
    if official is not None:
        if not isinstance(official, list) or not all(isinstance(x, str) for x in official):
            unknowns.append(
                "official_account_classes, when supplied, must be an array of strings."
            )
        elif selection_ok and selection not in official:
            failures.append(
                "The selected account class is not an exact entry in official_account_classes."
            )

    if failures:
        decision = "ineligible"
    elif unknowns:
        decision = "incomplete"
    else:
        decision = "eligible"

    return {
        "decision": decision,
        "failures": failures,
        "unknowns": unknowns,
        "personal_checking_count": count,
        "six_month_lookback_start": lookback.isoformat() if lookback else None,
        "desired_account_class": selection if selection_ok else None,
        "account_class_confirmed_exact": payload.get("account_class_confirmed_exact") is True,
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
        result = main(data)
    except json.JSONDecodeError:
        result = {
            "decision": "incomplete",
            "failures": [],
            "unknowns": ["stdin did not contain valid JSON."],
        }
    except Exception as exc:  # Preserve a JSON interface for the executor.
        result = {
            "decision": "incomplete",
            "failures": [],
            "unknowns": ["Assessment could not be completed: %s" % exc],
        }
    print(json.dumps(result, sort_keys=True))
